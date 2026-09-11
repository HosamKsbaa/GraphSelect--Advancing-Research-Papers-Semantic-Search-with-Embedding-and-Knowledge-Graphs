"""Adversarial Test Suite for Milestone M5: Section Synthesis Matrices (US4 / R4).

Empirically challenges:
1. Dimension boundary & fuzzing (rejects 1, 2, 6, 7; accepts 3, 4, 5; slug collisions; dirty strings).
2. LaTeX citekey regex fuzzing (bare DOIs, missing braces, invalid characters, injections).
3. Citation hallucination prevention ($CHR \\equiv 0.0\\%$, ungrounded DOIs, case sensitivity, zero side-effects).
4. Token budget stress under extreme load (5,000+ char evidence cells, table integrity, sanitization).
5. Fail-loud invariants and error handling in persistence and retrieval.

Complies with Constitution v2.2.1:
- C5, A15, A49: Auditability and zero side-effects on failure.
- C7: Complete static typing.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
- A37: Zero citation hallucination ($CHR \\equiv 0.0\\%$).
- SC-006: Under 800 token serialized markdown footprint.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from core.db.neo4j_service import Neo4jService
from core.errors.enhancement_errors import CitationHallucinationError, MatrixGenerationError
from features.drafting.dimension_deriver import (
    _slugify,
    derive_section_dimensions,
    validate_dimensions,
)
from features.drafting.matrix_models import (
    CITEKEY_PATTERN,
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    GenerateSectionSynthesisMatrixOutput,
    SectionSynthesisMatrix,
)
from features.drafting.matrix_persistence import (
    _count_tokens,
    _format_cell_content,
    _render_matrix_markdown,
    persist_matrix_to_neo4j,
    serialize_matrix_to_markdown,
)
from features.drafting.matrix_service import (
    MatrixService,
    assert_citation_grounding,
    extract_cell_evidence,
    format_doi_citekey,
    get_section_matrix_for_drafting,
)


def _make_dim(dim_id: str, name: str = "Dim", eval_type: str = "qualitative") -> AnalyticalDimension:
    """Helper to instantiate an AnalyticalDimension."""
    return AnalyticalDimension(
        dimension_id=dim_id, name=name, description="Test description", evaluation_type=eval_type
    )


def _make_cell(doi: str, text: str, metric: str | None = None) -> CellEvidenceExtract:
    """Helper to instantiate a valid CellEvidenceExtract."""
    clean = re.sub(r"[^a-zA-Z0-9]", "_", doi.lower()).strip("_")
    return CellEvidenceExtract(
        evidence_text=text,
        quantitative_metric=metric,
        citekey=f"\\cite{{doi_{clean}}}",
        is_grounded=True,
    )


def _make_matrix(
    section_id: str, dois: list[str], dims: list[AnalyticalDimension], cell_text: str = "Finding"
) -> SectionSynthesisMatrix:
    """Helper to build a SectionSynthesisMatrix with uniform cell data."""
    cell_data = {doi: {d.dimension_id: _make_cell(doi, cell_text) for d in dims} for doi in dois}
    return SectionSynthesisMatrix(
        matrix_id="mat-adv-1",
        section_id=section_id,
        section_title="Adversarial Title",
        narrative_theme="Adversarial Theme",
        dimensions=dims,
        assigned_dois=dois,
        verified_dois=dois,
        cell_data=cell_data,
        markdown_path=f"stage_04_artifacts/matrices/{section_id}.md",
    )


def test_validate_dimensions_rejects_boundary_1_and_2() -> None:
    """Reject 1 and 2 dimensions at lower boundary."""
    d1 = _make_dim("d1")
    d2 = _make_dim("d2")
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions([d1])
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions([d1, d2])


def test_validate_dimensions_rejects_boundary_6_and_7() -> None:
    """Reject 6 and 7 dimensions at upper boundary."""
    dims6 = [_make_dim(f"d_{i}") for i in range(6)]
    dims7 = [_make_dim(f"d_{i}") for i in range(7)]
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions(dims6)
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions(dims7)


def test_validate_dimensions_accepts_valid_counts_3_4_5() -> None:
    """Accept exact counts of 3, 4, and 5 dimensions."""
    for count in (3, 4, 5):
        dims = [_make_dim(f"d_{i}") for i in range(count)]
        validated = validate_dimensions(dims)
        assert len(validated) == count


def test_matrix_model_pydantic_rejects_invalid_dim_counts() -> None:
    """Ensure SectionSynthesisMatrix Pydantic model enforces 3..5 bounds."""
    dims_too_few = [_make_dim(f"d_{i}") for i in range(2)]
    dims_too_many = [_make_dim(f"d_{i}") for i in range(6)]
    with pytest.raises(ValidationError):
        _make_matrix("sec_few", ["10.1000/1"], dims_too_few)
    with pytest.raises(ValidationError):
        _make_matrix("sec_many", ["10.1000/1"], dims_too_many)


def test_slug_collision_on_normalized_names() -> None:
    """Detect slug collisions when different names resolve to same slug."""
    d1 = _make_dim("eval_metric", name="Eval Metric")
    d2 = _make_dim("eval_metric", name="Eval-Metric")
    d3 = _make_dim("d3", name="Third Dim")
    with pytest.raises(ValueError, match="Duplicate dimension slug detected"):
        validate_dimensions([d1, d2, d3])


def test_derive_dimensions_dirty_and_extreme_strings() -> None:
    """Verify derive_section_dimensions handles whitespace, symbols, and large prompts."""
    fuzzed_inputs = [
        ("", ""),
        ("   \t\n  ", "   "),
        ("§¶•ªº≠±!@#$%^&*()", "§¶•ªº"),
        ("IGNORE PREVIOUS INSTRUCTIONS" * 50, "DROP TABLE; SELECT *" * 50),
    ]
    for title, theme in fuzzed_inputs:
        dims = derive_section_dimensions(title, theme)
        assert 3 <= len(dims) <= 5
        assert len({d.dimension_id for d in dims}) == len(dims)


def test_validate_dimensions_rejects_corrupted_eval_types() -> None:
    """Validate rejection of unsupported or casing-corrupted evaluation types."""
    bad_types = ["numeric", "BENCHMARK", "QUALITATIVE", "", "metric\n", "ordinal"]
    for bad in bad_types:
        d1 = _make_dim("d1", eval_type="qualitative")
        d2 = _make_dim("d2", eval_type="metric")
        d3 = _make_dim("d3", eval_type=bad)
        with pytest.raises(ValueError, match="Invalid evaluation_type"):
            validate_dimensions([d1, d2, d3])


def test_citekey_pattern_accepts_academic_identifiers() -> None:
    """Accept valid canonical LaTeX citekeys matching CITEKEY_PATTERN."""
    valid_keys = [
        r"\cite{doi_10_1145_3543507_3583344}",
        r"\cite{doi_10_1016_j_jbi_2023_104381}",
        r"\cite{doi_10_1109_src65875_2025_11263707}",
        r"\cite{doi_10.1145/3543507.3583344}",
        r"\cite{doi_10_1000-182}",
    ]
    for k in valid_keys:
        assert CITEKEY_PATTERN.match(k) is not None, f"Should accept: {k}"


def test_citekey_pattern_rejects_bare_doi_and_missing_prefix() -> None:
    """Reject citekeys without LaTeX command or missing 'doi_' prefix."""
    invalid = [
        "10.1145/3543507.3583344",
        "doi:10.1145/3543507.3583344",
        r"\cite{10_1145_3543507}",
        r"\cite{paper_10_1145}",
        r"\cite{}",
    ]
    for k in invalid:
        assert CITEKEY_PATTERN.match(k) is None, f"Should reject: {k}"


def test_citekey_pattern_rejects_missing_or_nested_braces() -> None:
    """Reject malformed LaTeX braces and missing delimiters."""
    malformed = [
        r"\cite doi_10_1145",
        r"cite{doi_10_1145}",
        r"\cite{{doi_10_1145}}",
        r"\cite{doi_10_1145",
        r"\cite[p. 10]{doi_10_1145}",
    ]
    for k in malformed:
        assert CITEKEY_PATTERN.match(k) is None, f"Should reject: {k}"


def test_citekey_pattern_rejects_code_injection_and_whitespace() -> None:
    """Reject LaTeX command injections, whitespace, and shell metacharacters."""
    injections = [
        r"\cite{doi_10_1145}; DROP TABLE",
        r"\cite{doi_10_1145}\input{secret}",
        r"\cite{doi_10_1145\n}",
        r"\cite{doi_10 1145}",
        r"\cite{doi_10$1145}",
        r"\cite{doi_10#1145}",
    ]
    for k in injections:
        assert CITEKEY_PATTERN.match(k) is None, f"Should reject: {k}"


def test_cell_evidence_extract_pydantic_validation_error() -> None:
    """CellEvidenceExtract raises ValidationError on malformed citekeys."""
    bad_keys = ["bare_doi_10_1145", r"\cite{}", r"\cite{doi_}", r"\cite{doi_10 1145}"]
    for bad in bad_keys:
        with pytest.raises(ValidationError) as exc_info:
            CellEvidenceExtract(
                evidence_text="Valid text",
                citekey=bad,
            )
        assert "Invalid LaTeX citekey format" in str(exc_info.value)


def test_format_doi_citekey_cleanses_hostile_input() -> None:
    """Ensure format_doi_citekey strips hostile characters into valid citekey."""
    hostile_dois = [
        "  10.1145/3543507.3583344  ",
        "DOI:10.1109/SRC.2025!@#$",
        "10.1000/bad;input\n\t--attack",
    ]
    for h in hostile_dois:
        ck = format_doi_citekey(h)
        assert CITEKEY_PATTERN.match(ck) is not None, f"Failed for {h}: {ck}"


def test_grounding_assertion_raises_on_ungrounded_single_doi() -> None:
    """Raise CitationHallucinationError when single assigned DOI is missing."""
    found = {"10.1000/valid": {"doi": "10.1000/valid"}}
    assigned = ["10.1000/valid", "10.1000/hallucinated"]
    with pytest.raises(CitationHallucinationError) as exc_info:
        assert_citation_grounding(found, assigned, "sec_1")
    err = exc_info.value
    assert err.doi == "10.1000/hallucinated"
    assert err.http_status_code == 422


def test_grounding_assertion_raises_on_partially_grounded_set() -> None:
    """Raise CitationHallucinationError on 4 grounded and 1 ungrounded DOI."""
    found = {f"10.1000/{i}": {"doi": f"10.1000/{i}"} for i in range(4)}
    assigned = [f"10.1000/{i}" for i in range(5)]
    with pytest.raises(CitationHallucinationError) as exc_info:
        assert_citation_grounding(found, assigned, "sec_eval")
    assert exc_info.value.doi == "10.1000/4"
    assert "sec_eval" in str(exc_info.value)


def test_grounding_assertion_case_sensitivity_check() -> None:
    """Verify strict casing in grounding comparison raises if case differs."""
    found = {"10.1145/lower.case": {"doi": "10.1145/lower.case"}}
    assigned = ["10.1145/LOWER.CASE"]
    with pytest.raises(CitationHallucinationError) as exc_info:
        assert_citation_grounding(found, assigned, "sec_case")
    assert exc_info.value.doi == "10.1145/LOWER.CASE"


@pytest.mark.asyncio
async def test_generate_matrix_zero_side_effects_on_hallucination(tmp_path: Path) -> None:
    """Ensure CitationHallucinationError aborts without disk or Neo4j writes."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_read = AsyncMock(return_value=[])
    mock_neo4j.execute_write = AsyncMock()
    service = MatrixService(neo4j=mock_neo4j)
    inp = GenerateSectionSynthesisMatrixInput(
        project_id="p1", section_id="sec_hallucinated",
        section_title="Title", narrative_theme="Theme",
        assigned_dois=["10.1000/fake_doi"], run_id="run_1",
    )
    with pytest.raises(CitationHallucinationError):
        await service.generate_section_matrix(inp)
    mock_neo4j.execute_write.assert_not_called()
    target_md = Path(f"stage_04_artifacts/matrices/{inp.section_id}.md")
    assert not target_md.exists()


def test_token_budget_bounds_with_5000_char_cells(tmp_path: Path) -> None:
    """Ensure matrix with 5,000+ char evidence cells stays under 800 tokens."""
    dims = [_make_dim(f"dim_{i}", f"Dimension {i}") for i in range(4)]
    huge_text = "Dense academic claim and methodology extract. " * 120
    assert len(huge_text) > 5000
    dois = [f"10.1000/paper_{i}" for i in range(3)]
    matrix = _make_matrix("sec_huge", dois, dims, cell_text=huge_text)
    written_path = serialize_matrix_to_markdown(matrix, output_dir=str(tmp_path))
    content = Path(written_path).read_text(encoding="utf-8")
    tokens = _count_tokens(content)
    assert tokens < 800, f"Token count exceeded: {tokens}"
    assert "| Paper (Citekey) |" in content
    assert len(content.strip().splitlines()) >= 5


def test_cell_formatting_escapes_pipes_and_newlines() -> None:
    """Ensure _format_cell_content neutralizes table-breaking characters."""
    raw_evidence = "Row 1 | Cell 2\nRow 2 with more | pipe symbols\nEnd line"
    cell = CellEvidenceExtract(
        evidence_text=raw_evidence,
        quantitative_metric="p < 0.01",
        citekey=r"\cite{doi_10_1000_test}",
    )
    formatted = _format_cell_content(cell, max_chars=250)
    assert "\n" not in formatted
    assert formatted.count(r"\|") >= 2
    assert formatted.count(" | ") == 0
    assert "**p < 0.01**:" in formatted


def test_extract_cell_evidence_empty_and_whitespace_abstract() -> None:
    """Verify cell evidence extractor gracefully handles blank abstracts."""
    dim = _make_dim("eval_dim", "Evaluation Dimension", "metric")
    blank_inputs = ["", "   ", "\n\t  \r\n"]
    for blank in blank_inputs:
        extract = extract_cell_evidence("10.1145/test_doi", blank, dim)
        assert extract.is_grounded is True
        assert extract.quantitative_metric is None
        assert CITEKEY_PATTERN.match(extract.citekey) is not None
        assert "Synthesized finding for Evaluation Dimension" in extract.evidence_text


@pytest.mark.asyncio
async def test_persist_matrix_to_neo4j_raises_on_zero_rows() -> None:
    """Verify persist_matrix_to_neo4j fails loudly if Cypher returns 0 rows."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    dims = [_make_dim(f"d_{i}") for i in range(3)]
    matrix = _make_matrix("sec_zero", ["10.1000/1"], dims)
    with pytest.raises(MatrixGenerationError, match="Fail-loud grounding failure"):
        await persist_matrix_to_neo4j(mock_neo4j, matrix, run_id="run_0")


@pytest.mark.asyncio
async def test_persist_matrix_to_neo4j_raises_on_count_mismatch() -> None:
    """Verify persist_matrix_to_neo4j fails loudly if persisted != expected count."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(return_value=[{"persisted_count": 2}])
    dims = [_make_dim(f"d_{i}") for i in range(3)]
    matrix = _make_matrix("sec_mismatch", ["10.1000/1"], dims)
    with pytest.raises(MatrixGenerationError, match="Persisted count mismatch"):
        await persist_matrix_to_neo4j(mock_neo4j, matrix, run_id="run_0")


def test_get_section_matrix_for_drafting_raises_file_not_found() -> None:
    """Verify get_section_matrix_for_drafting raises FileNotFoundError for missing path."""
    with pytest.raises(FileNotFoundError, match="Section matrix artifact not found"):
        get_section_matrix_for_drafting("nonexistent_section_id_xyz")


def test_matrix_input_model_rejects_empty_assigned_dois() -> None:
    """Verify GenerateSectionSynthesisMatrixInput rejects empty DOI lists."""
    with pytest.raises(ValidationError):
        GenerateSectionSynthesisMatrixInput(
            project_id="proj_1",
            section_id="sec_1",
            section_title="Title",
            narrative_theme="Theme",
            assigned_dois=[],
            run_id="run_1",
        )
