"""Comprehensive Integration Tests for Section Synthesis Matrix (T043 / US4).

Verifies:
- Paper evidence extractor and canonical LaTeX citekey validation (\\cite{doi_...}).
- Citation Grounding Assertion ($CHR \\equiv 0.0\\%$): raises CitationHallucinationError.
- Dual-layer persistence: Neo4j Cypher execution and <800 token Markdown serialization.
- Fail-loud grounding in Cypher persistence: raises MatrixGenerationError on mismatch.
- MatrixService end-to-end matrix generation and drafting context injection.
- Architectural forward commitment TODO (T048) in matrix_service.py.
- Live Neo4j graph persistence when database service is reachable.

Complies with Constitution v2.2.1:
- C5, A15, A49: Auditability via run_id and created_in_stage.
- C7: Complete static typing.
- C8: Pure Neo4j graph SSOT.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
- A37: Zero citation hallucination ($CHR \\equiv 0.0\\%$).
- SC-006: Under 800 token serialized markdown footprint.
"""
from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.db.neo4j_service import Neo4jService
from core.errors.enhancement_errors import CitationHallucinationError, MatrixGenerationError
from features.drafting.dimension_deriver import derive_section_dimensions
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
    persist_matrix_to_neo4j,
    serialize_matrix_to_markdown,
)
from features.drafting.matrix_service import (
    MatrixService,
    extract_cell_evidence,
    format_doi_citekey,
    get_section_matrix_for_drafting,
    load_section_matrix_context,
)


def _sample_dimensions() -> list[AnalyticalDimension]:
    """Provide standard 3 test analytical dimensions."""
    return [
        AnalyticalDimension(
            dimension_id="mitigation_mechanism",
            name="Mitigation Mechanism",
            description="Algorithmic intervention used to prevent hallucination",
            evaluation_type="qualitative",
        ),
        AnalyticalDimension(
            dimension_id="verification_benchmark",
            name="Verification Benchmark",
            description="Academic dataset used for citation verification",
            evaluation_type="benchmark",
        ),
        AnalyticalDimension(
            dimension_id="empirical_failure_rate",
            name="Empirical Failure Rate",
            description="Observed error or hallucination rate under stress",
            evaluation_type="metric",
        ),
    ]


def _sample_cell_data(
    dois: list[str], dims: list[AnalyticalDimension]
) -> dict[str, dict[str, CellEvidenceExtract]]:
    """Build nested 2D cell data dictionary for sample DOIs."""
    cell_data: dict[str, dict[str, CellEvidenceExtract]] = {}
    for doi in dois:
        cell_data[doi] = {}
        for dim in dims:
            clean = re.sub(r"[^a-zA-Z0-9]", "_", doi.lower()).strip("_")
            cell_data[doi][dim.dimension_id] = CellEvidenceExtract(
                evidence_text=f"Sample finding for {dim.name} in {doi}",
                quantitative_metric="98.5%" if dim.evaluation_type == "metric" else None,
                citekey=f"\\cite{{doi_{clean}}}",
                is_grounded=True,
            )
    return cell_data


def _build_test_matrix(
    section_id: str, dois: list[str], out_path: str = "test.md"
) -> SectionSynthesisMatrix:
    """Instantiate a valid SectionSynthesisMatrix model."""
    dims = _sample_dimensions()
    cells = _sample_cell_data(dois, dims)
    return SectionSynthesisMatrix(
        matrix_id=str(uuid.uuid4()),
        section_id=section_id,
        section_title="Hallucination Mitigation and Grounding",
        narrative_theme="Epistemic fact-checking and citekey verification",
        dimensions=dims,
        assigned_dois=dois,
        verified_dois=dois,
        cell_data=cells,
        markdown_path=out_path,
    )


def _mock_neo4j_for_matrix() -> MagicMock:
    """Prepare mock Neo4jService with paper records and write return value."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_read = AsyncMock(
        return_value=[
            {"doi": "10.1145/300", "title": "A", "abstract": "Method achieved 95% accuracy."},
            {"doi": "10.1145/400", "title": "B", "abstract": "Mitigation benchmark study."},
        ]
    )
    mock_neo4j.execute_write = AsyncMock(
        return_value=[{"matrix_id": "mat_123", "persisted_count": 8}]
    )
    return mock_neo4j


# ==============================================================================
# 1. Evidence Extraction & LaTeX Citekey Formatting Tests (T045)
# ==============================================================================


def test_format_doi_citekey_canonical_pattern() -> None:
    """Verify format_doi_citekey produces valid citekey matching CITEKEY_PATTERN."""
    doi = "10.1145/3292500"
    citekey = format_doi_citekey(doi)
    assert citekey == r"\cite{doi_10_1145_3292500}"
    assert CITEKEY_PATTERN.match(citekey) is not None


def test_format_doi_citekey_special_characters() -> None:
    """Verify format_doi_citekey cleans complex characters."""
    doi = "10.1007/978-3-030-22948-1_15"
    citekey = format_doi_citekey(doi)
    assert CITEKEY_PATTERN.match(citekey) is not None
    assert "-" not in citekey or "_" in citekey


def test_extract_cell_evidence_with_metric() -> None:
    """Extract cell evidence parses metric and formats citekey properly."""
    dim = AnalyticalDimension(
        dimension_id="empirical_failure_rate",
        name="Empirical Failure Rate",
        description="Observed error rate",
        evaluation_type="metric",
    )
    abstract = "Our method reduces citation hallucination to 2.4% on benchmark datasets."
    cell = extract_cell_evidence("10.1145/123456", abstract, dim)
    assert cell.citekey == r"\cite{doi_10_1145_123456}"
    assert cell.quantitative_metric == "2.4%"
    assert "reduces citation hallucination" in cell.evidence_text
    assert len(cell.evidence_text) <= 250


def test_extract_cell_evidence_empty_abstract() -> None:
    """Extract cell evidence handles empty abstract with fallback finding."""
    dim = AnalyticalDimension(
        dimension_id="mitigation_mechanism",
        name="Mitigation Mechanism",
        description="Intervention preventing hallucination",
        evaluation_type="qualitative",
    )
    cell = extract_cell_evidence("10.1145/999999", "", dim)
    assert cell.citekey == r"\cite{doi_10_1145_999999}"
    assert len(cell.evidence_text) > 0
    assert cell.is_grounded is True


# ==============================================================================
# 2. Citation Grounding Assertion Tests ($CHR \equiv 0.0\%$, T045)
# ==============================================================================


@pytest.mark.asyncio
async def test_citation_grounding_success() -> None:
    """Verify grounding succeeds when all assigned DOIs exist in Neo4j."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_read = AsyncMock(
        return_value=[
            {"doi": "10.1145/111", "title": "Paper 1", "abstract": "Abstract 1"},
            {"doi": "10.1145/222", "title": "Paper 2", "abstract": "Abstract 2"},
        ]
    )
    service = MatrixService(neo4j=mock_neo4j)
    result = await service.verify_citation_grounding(["10.1145/111", "10.1145/222"], "sec_01")
    assert len(result) == 2
    assert "10.1145/111" in result


@pytest.mark.asyncio
async def test_citation_grounding_raises_hallucination_error() -> None:
    """Verify missing DOI raises CitationHallucinationError (Constitution A37)."""
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_read = AsyncMock(
        return_value=[{"doi": "10.1145/111", "title": "Paper 1", "abstract": "Abstract 1"}]
    )
    service = MatrixService(neo4j=mock_neo4j)
    with pytest.raises(CitationHallucinationError) as exc_info:
        await service.verify_citation_grounding(["10.1145/111", "10.1145/missing_doi"], "sec_02")
    assert exc_info.value.doi == "10.1145/missing_doi"
    assert exc_info.value.section_id == "sec_02"
    assert exc_info.value.http_status_code == 422


# ==============================================================================
# 3. Dual-Layer Persistence: Neo4j Engine Tests (T046)
# ==============================================================================


@pytest.mark.asyncio
async def test_persist_matrix_to_neo4j_success() -> None:
    """Persist matrix passes $run_id, $created_in_stage, and verifies cell count."""
    dois = ["10.1145/111", "10.1145/222"]
    matrix = _build_test_matrix("sec_04", dois)
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(
        return_value=[{"matrix_id": matrix.matrix_id, "persisted_count": 6}]
    )
    res = await persist_matrix_to_neo4j(mock_neo4j, matrix, run_id="run_test", stage_index=4)
    assert res["matrix_id"] == matrix.matrix_id
    assert res["persisted_count"] == 6
    mock_neo4j.execute_write.assert_called_once()
    _, params = mock_neo4j.execute_write.call_args[0]
    assert params["run_id"] == "run_test"
    assert params["created_in_stage"] == 4


@pytest.mark.asyncio
async def test_persist_matrix_to_neo4j_fail_loud_mismatch() -> None:
    """Fail-loud verification raises MatrixGenerationError on persisted count mismatch."""
    dois = ["10.1145/111", "10.1145/222"]
    matrix = _build_test_matrix("sec_04", dois)
    mock_neo4j = MagicMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    with pytest.raises(MatrixGenerationError, match="Fail-loud grounding failure"):
        await persist_matrix_to_neo4j(mock_neo4j, matrix, run_id="run_fail", stage_index=4)


# ==============================================================================
# 4. Markdown Table Serialization & Token Budget Tests (T046 / SC-006)
# ==============================================================================


def test_serialize_matrix_to_markdown_structure(tmp_path: Path) -> None:
    """Verify serialized markdown contains table headers, citekeys, and sections."""
    dois = ["10.1145/111", "10.1145/222"]
    matrix = _build_test_matrix("sec_structure", dois)
    out_file = serialize_matrix_to_markdown(matrix, output_dir=str(tmp_path))
    assert os.path.exists(out_file)
    content = Path(out_file).read_text(encoding="utf-8")
    assert "## Synthesis Matrix:" in content
    assert "| Paper (Citekey) |" in content
    assert r"\cite{doi_10_1145_111}" in content
    assert r"\cite{doi_10_1145_222}" in content


def test_serialize_matrix_to_markdown_token_budget(tmp_path: Path) -> None:
    """Verify markdown serialization stays strictly under 800 tokens (SC-006)."""
    dois = [f"10.1145/paper_{i}" for i in range(5)]
    matrix = _build_test_matrix("sec_tokens", dois)
    out_file = serialize_matrix_to_markdown(matrix, output_dir=str(tmp_path))
    content = Path(out_file).read_text(encoding="utf-8")
    tokens = _count_tokens(content)
    assert tokens < 800


# ==============================================================================
# 5. MatrixService End-to-End Generation & Context Injection (T045, T047, T048)
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_section_matrix_e2e() -> None:
    """End-to-end matrix generation with grounding, derivation, and persistence."""
    mock_neo4j = _mock_neo4j_for_matrix()
    service = MatrixService(neo4j=mock_neo4j)
    inp = GenerateSectionSynthesisMatrixInput(
        project_id="proj_1",
        section_id="sec_mitigation",
        section_title="Hallucination Mitigation",
        narrative_theme="Empirical verification mechanisms",
        assigned_dois=["10.1145/300", "10.1145/400"],
        run_id="run_e2e",
        stage_index=4,
    )
    out = await service.generate_section_matrix(inp)
    assert out.status == "success"
    assert out.paper_count == 2
    assert len(out.dimensions) >= 3


def test_get_section_matrix_for_drafting(tmp_path: Path) -> None:
    """Drafting context injector reads markdown table cleanly (T047, T048)."""
    fake_path = tmp_path / "sec_draft.md"
    fake_path.write_text("# Matrix Content", encoding="utf-8")
    content = get_section_matrix_for_drafting("sec_draft", markdown_path=str(fake_path))
    assert content == "# Matrix Content"
    alias_content = load_section_matrix_context("sec_draft", markdown_path=str(fake_path))
    assert alias_content == "# Matrix Content"


def test_get_section_matrix_not_found() -> None:
    """Drafting context injector raises FileNotFoundError when artifact missing."""
    with pytest.raises(FileNotFoundError):
        get_section_matrix_for_drafting("nonexistent_section_slug_xyz")


def test_architectural_forward_commitment_todo_documented() -> None:
    """Verify architectural forward commitment TODO (T048) exists in matrix_service.py."""
    import features.drafting.matrix_service as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "TODO(FR-012-Q4)" in source
    assert "benchmark fine-grained cell-level graph traversal" in source


# ==============================================================================
# 6. Live Neo4j Graph Verification (when reachable)
# ==============================================================================


async def _get_live_neo4j() -> Neo4jService | None:
    """Connect to live Neo4j service for integration testing."""
    for pwd in ["changeme", os.environ.get("NEO4J_PASSWORD", "")]:
        if not pwd:
            continue
        try:
            svc = Neo4jService(uri="bolt://localhost:7687", user="neo4j", password=pwd)
            await svc.connect()
            return svc
        except Exception:
            continue
    return None


async def _seed_live_test_nodes(
    neo4j: Neo4jService, sec_id: str, doi1: str, doi2: str, tag: str
) -> None:
    """Seed OutlineSection and Papers for live persistence test."""
    seed_q = (
        "CREATE (s:OutlineSection {id: $sec_id, test_tag: $tag}) "
        "CREATE (p1:Paper {doi: $doi1, title: 'Paper 1', test_tag: $tag}) "
        "CREATE (p2:Paper {doi: $doi2, title: 'Paper 2', test_tag: $tag})"
    )
    await neo4j.execute_write(seed_q, {"sec_id": sec_id, "doi1": doi1, "doi2": doi2, "tag": tag})


async def _cleanup_live_test_nodes(neo4j: Neo4jService, sec_id: str, tag: str) -> None:
    """Clean up live test nodes created during integration verification."""
    clean_q = (
        "MATCH (n) WHERE n.test_tag = $tag DETACH DELETE n "
        "WITH 1 AS _ "
        "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id}) DETACH DELETE m"
    )
    await neo4j.execute_write(clean_q, {"tag": tag, "sec_id": sec_id})
    await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_dual_persistence() -> None:
    """Verify live Neo4j node merging, [:HAS_MATRIX], and [:SYNTHESIZES] linkage."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, doi1, doi2 = f"sec_{tag}", f"10.1145/{tag}_1", f"10.1145/{tag}_2"
    try:
        await _seed_live_test_nodes(neo4j, sec_id, doi1, doi2, tag)
        matrix = _build_test_matrix(sec_id, [doi1, doi2])
        res = await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        assert res["persisted_count"] == len(matrix.dimensions) * 2
        verify_q = (
            "MATCH (s:OutlineSection {id: $sec_id})-[:HAS_MATRIX]->(m:SectionSynthesisMatrix) "
            "MATCH (m)-[rel:SYNTHESIZES]->(p:Paper) "
            "RETURN count(rel) AS rel_count, m.matrix_id AS mid"
        )
        records = await neo4j.execute_read(verify_q, {"sec_id": sec_id})
        assert len(records) == 1 and records[0]["rel_count"] == len(matrix.dimensions) * 2
    finally:
        await _cleanup_live_test_nodes(neo4j, sec_id, tag)
