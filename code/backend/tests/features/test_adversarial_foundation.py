"""Adversarial Stress Test Suite for Milestone M1 Foundation Models, Errors & Schema.

Empirically tests edge cases, extreme values, boundary conditions, regex adherence,
malformed inputs, and security payloads against:
- Ingestion Models (UserIngestedPaper, TitleConfirmationChip, IngestUserPaperInput)
- SVPL Multi-Hop Models (MultiHopAuthorization, BridgeHopCandidate, MultiHopBridgePathway, SVPLMultiHopDiscoveryInput)
- Gap Analysis Models (GapRemediationCycle, RunAutonomousGapRemediationInput)
- Section Synthesis Matrix Models (CellEvidenceExtract, SectionSynthesisMatrix)
- Enhancement Error Taxonomy & HTTP Status Code Mappings
- Neo4j Schema Invariants and Vector Index Configurations
"""
from __future__ import annotations

import math
import pytest
from pydantic import ValidationError

from core.db.neo4j_schema import (
    COMPOSITE_INDEXES,
    UNIQUENESS_CONSTRAINTS,
    VECTOR_INDEXES,
)
from core.errors.enhancement_errors import (
    ERROR_STATUS_CODE_MAP,
    CitationHallucinationError,
    CoverageEvaluationError,
    DuplicatePaperError,
    EnhancementToolError,
    MatrixGenerationError,
    MultiHopUnauthorizedError,
    TitleConfirmationRequiredError,
    UnresolvableIdentifierError,
    get_http_status_code,
)
from features.drafting.matrix_models import (
    CITEKEY_PATTERN,
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    GenerateSectionSynthesisMatrixOutput,
    SectionSynthesisMatrix,
)
from features.gap_analysis.models import (
    GapRemediationCycle,
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
    RunAutonomousGapRemediationOutput,
)
from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    ConfirmTitleIngestionOutput,
    IdentifierType,
    IngestUserPaperInput,
    IngestUserPaperOutput,
    IngestionSource,
    TitleConfirmationChip,
    UserIngestedPaper,
)
from features.ranking.svpl_models import (
    BridgeHopCandidate,
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopAuthorization,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
    SVPLMultiHopDiscoveryInput,
    SVPLMultiHopDiscoveryOutput,
)


# ============================================================================
# 1. ADVERSARIAL INGESTION & DOI TESTS
# ============================================================================


@pytest.mark.parametrize(
    ("raw_input", "expected_doi"),
    [
        ("https://doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("http://doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("https://dx.doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("http://dx.doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("dx.doi.org/10.1109/5.771073", "10.1109/5.771073"),
        ("HTTPS://DOI.ORG/10.1109/5.771073", "10.1109/5.771073"),
        ("   10.1109/5.771073   ", "10.1109/5.771073"),
        ("10.1000/182-XYZ", "10.1000/182-xyz"),
        ("10.12", "10.12"),  # Exact 5-char boundary
    ],
)
def test_user_ingested_paper_doi_normalization_edge_cases(raw_input: str, expected_doi: str) -> None:
    """Verify various valid DOI URL prefixes and case/whitespace normalizations."""
    paper = UserIngestedPaper(raw_identifier=raw_input, doi=raw_input, title="Valid Title")
    assert paper.doi == expected_doi


@pytest.mark.parametrize(
    "invalid_doi",
    [
        "",  # Empty string
        "    ",  # Whitespace only
        "10.",  # Too short (length 3 < min_length 5)
        "10.1",  # Too short (length 4 < min_length 5)
        "11.1145/3292500",  # Non-10. prefix
        "not_a_doi_at_all",  # Arbitrary string
        "arxiv:2301.12345",  # ArXiv ID
        "https://arxiv.org/abs/2301.12345",  # ArXiv URL
        "ftp://doi.org/10.1145/3292500",  # Non-HTTP protocol
        "https://fake-doi.org/10.1145/3292500",  # Spoofed domain
        "doi:10.1145/3292500",  # Missing prefix stripping for bare doi:
        "https://doi.org/https://doi.org/10.1145/1",  # Chained URL prefixes
    ],
)
def test_user_ingested_paper_invalid_doi_rejected(invalid_doi: str) -> None:
    """Verify that invalid or malformed DOIs raise ValidationError."""
    with pytest.raises(ValidationError):
        UserIngestedPaper(raw_identifier=invalid_doi, doi=invalid_doi, title="Title")


def test_user_ingested_paper_year_boundaries() -> None:
    """Verify year boundaries [1900, 2100]."""
    # Valid boundaries
    p_1900 = UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=1900)
    assert p_1900.year == 1900

    p_2100 = UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=2100)
    assert p_2100.year == 2100

    p_none = UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=None)
    assert p_none.year is None

    # Invalid boundaries
    with pytest.raises(ValidationError):
        UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=1899)

    with pytest.raises(ValidationError):
        UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=2101)

    with pytest.raises(ValidationError):
        UserIngestedPaper(raw_identifier="10.1/a", doi="10.1/a", title="T", year=-1)


@pytest.mark.parametrize(
    "extreme_similarity",
    [
        1.00000001,
        -0.00000001,
        100.0,
        -100.0,
        float("inf"),
        float("-inf"),
    ],
)
def test_title_confirmation_chip_similarity_extremes(extreme_similarity: float) -> None:
    """Verify TitleConfirmationChip rejects similarity_score outside [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-x",
            extracted_title="Extracted Title",
            resolved_openalex_id="W123",
            resolved_title="Resolved Title",
            similarity_score=extreme_similarity,
        )


def test_title_confirmation_chip_nan_rejected() -> None:
    """Verify TitleConfirmationChip rejects NaN similarity_score."""
    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-nan",
            extracted_title="Extracted Title",
            resolved_openalex_id="W123",
            resolved_title="Resolved Title",
            similarity_score=float("nan"),
        )


def test_title_confirmation_chip_title_boundary() -> None:
    """Verify TitleConfirmationChip requires extracted_title min_length=3."""
    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-1",
            extracted_title="",
            resolved_openalex_id="W123",
            resolved_title="Resolved Title",
            similarity_score=0.95,
        )

    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-1",
            extracted_title="ab",
            resolved_openalex_id="W123",
            resolved_title="Resolved Title",
            similarity_score=0.95,
        )

    chip_3 = TitleConfirmationChip(
        chip_id="chip-1",
        extracted_title="abc",
        resolved_openalex_id="W123",
        resolved_title="Resolved Title",
        similarity_score=0.95,
    )
    assert chip_3.extracted_title == "abc"


def test_ingest_paper_input_missing_required_fields() -> None:
    """Verify IngestUserPaperInput requires project_id and run_id."""
    with pytest.raises(ValidationError):
        IngestUserPaperInput(identifier="10.1145/1")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        IngestUserPaperInput(identifier="10.1145/1", project_id="p1")  # type: ignore[call-arg]


# ============================================================================
# 2. ADVERSARIAL SVPL MULTI-HOP TESTS
# ============================================================================


def test_multihop_authorization_context_description_boundary() -> None:
    """Verify MultiHopAuthorization context_description length boundary (min_length=10)."""
    # 9 chars -> Fails
    with pytest.raises(ValidationError):
        MultiHopAuthorization(
            trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
            requester="User",
            context_description="123456789",
        )

    # 10 chars -> Passes
    auth_10 = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
        requester="User",
        context_description="1234567890",
    )
    assert auth_10.context_description == "1234567890"


@pytest.mark.parametrize("invalid_hop", [-2, -1, 0, 4, 5, 10])
def test_bridge_hop_candidate_invalid_hop_level(invalid_hop: int) -> None:
    """Verify BridgeHopCandidate hop_level is strictly constrained to [1, 3]."""
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="Title",
            hop_level=invalid_hop,
            cosine_similarity=0.5,
            adaptive_threshold_tau=0.5,
        )


@pytest.mark.parametrize(
    "extreme_cosine",
    [-1.0001, 1.0001, -2.0, 2.0, float("inf"), float("-inf")],
)
def test_bridge_hop_candidate_cosine_similarity_extremes(extreme_cosine: float) -> None:
    """Verify BridgeHopCandidate cosine_similarity is strictly constrained to [-1.0, 1.0]."""
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="Title",
            hop_level=1,
            cosine_similarity=extreme_cosine,
            adaptive_threshold_tau=0.5,
        )


def test_bridge_hop_candidate_nan_cosine_rejected() -> None:
    """Verify BridgeHopCandidate rejects NaN cosine similarity."""
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="Title",
            hop_level=1,
            cosine_similarity=float("nan"),
            adaptive_threshold_tau=0.5,
        )


def test_bridge_hop_candidate_negative_pagerank_rejected() -> None:
    """Verify BridgeHopCandidate rejects negative pagerank_score."""
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="Title",
            hop_level=1,
            cosine_similarity=0.5,
            pagerank_score=-0.0001,
            adaptive_threshold_tau=0.5,
        )


@pytest.mark.parametrize("invalid_layer", [-1, 4, 5])
def test_multihop_pathway_layer_bounds(invalid_layer: int) -> None:
    """Verify MultiHopBridgePathway discovered_layer is strictly [0, 3]."""
    with pytest.raises(ValidationError):
        MultiHopBridgePathway(
            pathway_id="p-1",
            source_doi="10.1/1",
            target_doi="10.1/2",
            mechanism=BridgeMechanism.DIRECTED_2HOP,
            discovered_layer=invalid_layer,
            confidence=0.8,
            hop_distance=2,
        )


@pytest.mark.parametrize("invalid_confidence", [-0.01, 1.01, float("inf"), float("-inf")])
def test_multihop_pathway_confidence_bounds(invalid_confidence: float) -> None:
    """Verify MultiHopBridgePathway confidence is strictly [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        MultiHopBridgePathway(
            pathway_id="p-1",
            source_doi="10.1/1",
            target_doi="10.1/2",
            mechanism=BridgeMechanism.DIRECTED_2HOP,
            discovered_layer=1,
            confidence=invalid_confidence,
            hop_distance=2,
        )


# ============================================================================
# 3. ADVERSARIAL GAP REMEDIATION TESTS
# ============================================================================


@pytest.mark.parametrize("invalid_iteration", [0, 4, 5, -1])
def test_gap_remediation_cycle_iteration_bounds(invalid_iteration: int) -> None:
    """Verify GapRemediationCycle iteration is strictly [1, 3]."""
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c-1",
            iteration=invalid_iteration,
            target_rq_id="rq-1",
            initial_coverage=0.3,
            queries_generated=["query 1"],
            resulting_coverage=0.6,
            coverage_delta=0.3,
            status=RemediationCycleStatus.IN_PROGRESS,
        )


def test_gap_remediation_cycle_queries_bounds() -> None:
    """Verify GapRemediationCycle queries_generated length is strictly [1, 5]."""
    # 0 queries -> Fails
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c-1",
            iteration=1,
            target_rq_id="rq-1",
            initial_coverage=0.3,
            queries_generated=[],
            resulting_coverage=0.6,
            coverage_delta=0.3,
            status=RemediationCycleStatus.IN_PROGRESS,
        )

    # 6 queries -> Fails
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c-1",
            iteration=1,
            target_rq_id="rq-1",
            initial_coverage=0.3,
            queries_generated=[f"q{i}" for i in range(6)],
            resulting_coverage=0.6,
            coverage_delta=0.3,
            status=RemediationCycleStatus.IN_PROGRESS,
        )

    # 1 and 5 queries -> Pass
    c_1 = GapRemediationCycle(
        cycle_id="c-1",
        iteration=1,
        target_rq_id="rq-1",
        initial_coverage=0.3,
        queries_generated=["q1"],
        resulting_coverage=0.6,
        coverage_delta=0.3,
        status=RemediationCycleStatus.IN_PROGRESS,
    )
    assert len(c_1.queries_generated) == 1

    c_5 = GapRemediationCycle(
        cycle_id="c-5",
        iteration=1,
        target_rq_id="rq-1",
        initial_coverage=0.3,
        queries_generated=[f"q{i}" for i in range(5)],
        resulting_coverage=0.6,
        coverage_delta=0.3,
        status=RemediationCycleStatus.IN_PROGRESS,
    )
    assert len(c_5.queries_generated) == 5


def test_gap_remediation_cycle_retrieved_candidates_max_bound() -> None:
    """Verify GapRemediationCycle retrieved_candidate_dois max_length is 3."""
    # 4 candidates -> Fails
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c-1",
            iteration=1,
            target_rq_id="rq-1",
            initial_coverage=0.3,
            queries_generated=["q1"],
            retrieved_candidate_dois=["10.1/1", "10.1/2", "10.1/3", "10.1/4"],
            resulting_coverage=0.6,
            coverage_delta=0.3,
            status=RemediationCycleStatus.IN_PROGRESS,
        )


@pytest.mark.parametrize("invalid_max_iter", [0, 4, -1])
def test_run_gap_remediation_input_iteration_bounds(invalid_max_iter: int) -> None:
    """Verify RunAutonomousGapRemediationInput max_iterations is strictly [1, 3]."""
    with pytest.raises(ValidationError):
        RunAutonomousGapRemediationInput(
            project_id="p-1",
            rq_id="rq-1",
            max_iterations=invalid_max_iter,
            run_id="r-1",
        )


# ============================================================================
# 4. ADVERSARIAL SECTION SYNTHESIS MATRIX & CITEKEY TESTS
# ============================================================================


@pytest.mark.parametrize(
    "valid_citekey",
    [
        r"\cite{doi_10_1145_3292500}",
        r"\cite{doi_10.1145/3292500}",
        r"\cite{doi_10-1145-3292500}",
        r"\cite{doi_10.1007/978-3-030-22948-0_19}",
        r"\cite{doi_w123456789}",
        r"\cite{doi_arxiv_2301.12345}",
        r"\cite{doi_10.1016/j.knosys.2024.100}",
        r"\cite{doi_10_1}",
    ],
)
def test_cell_evidence_extract_valid_citekeys(valid_citekey: str) -> None:
    """Verify canonical valid LaTeX citekey formats match regex."""
    extract = CellEvidenceExtract(
        evidence_text="Valid evidence quote",
        citekey=valid_citekey,
    )
    assert extract.citekey == valid_citekey
    assert CITEKEY_PATTERN.match(valid_citekey) is not None


@pytest.mark.parametrize(
    "adversarial_citekey",
    [
        "cite{doi_10_1145_1}",  # Missing leading backslash
        r"\cite{doi_10_1145_1",  # Missing closing brace
        r"\citedoi_10_1145_1}",  # Missing opening brace
        r"\cite{{doi_10_1145_1}}",  # Double braces
        r"\cite{ doi_10_1145_1 }",  # Spaces inside braces
        r"\cite{doi_10_1145_1 2}",  # Space inside identifier
        r"\cite{doi_10_1145\t1}",  # Tab character
        r"\cite{doi_10_1145\n1}",  # Newline character
        r"\cite{10.1145/3292500}",  # Missing doi_ prefix
        r"\cite{ref_10_1145_3292500}",  # Wrong prefix ref_
        r"\cite{DOI_10_1145_3292500}",  # Uppercase prefix DOI_
        r"\cite{doi_}",  # Bare prefix with no identifier
        r"\cite{}",  # Empty cite
        r"\cite{doi_10.1002/(sici)1097}",  # Parentheses in DOI
        r"\cite{doi_10.1000/test;1}",  # Semicolon in DOI
        r"\cite{doi_10.1000/test:1}",  # Colon in DOI
        r"\cite{doi_paper1,doi_paper2}",  # Comma-separated multiple citations
        r"\cite{doi_10.1000/a&b}",  # Ampersand in DOI
        r"\cite{doi_10.1000/%20}",  # Percent sign in DOI
        r"\cite{doi_10.1000/[test]}",  # Square brackets in DOI
        r"\cite{doi_\textbf{bold}}",  # LaTeX macro injection
        "[@doi_10.1145/3292500]",  # Pandoc markdown citation format
        "(Smith et al., 2024)",  # Author-year string
        "10.1145/3292500",  # Raw unadorned DOI
    ],
)
def test_cell_evidence_extract_adversarial_citekeys_rejected(adversarial_citekey: str) -> None:
    """Verify that malformed, unescaped, or injected citekeys raise ValidationError."""
    with pytest.raises(ValidationError):
        CellEvidenceExtract(
            evidence_text="Sample evidence quote",
            citekey=adversarial_citekey,
        )


def test_cell_evidence_extract_empty_evidence_rejected() -> None:
    """Verify CellEvidenceExtract rejects empty evidence_text."""
    with pytest.raises(ValidationError):
        CellEvidenceExtract(
            evidence_text="",
            citekey=r"\cite{doi_10_1145_1}",
        )


@pytest.mark.parametrize("dim_count", [0, 1, 2, 6, 7, 10])
def test_section_synthesis_matrix_dimension_count_boundaries(dim_count: int) -> None:
    """Verify SectionSynthesisMatrix strictly rejects dimension counts < 3 or > 5."""
    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(dim_count)
    ]
    with pytest.raises(ValidationError):
        SectionSynthesisMatrix(
            matrix_id="m-1",
            section_id="sec-1",
            section_title="Title",
            narrative_theme="Theme",
            dimensions=dims,
            assigned_dois=["10.1/1"],
            cell_data={},
            markdown_path="path.md",
        )


@pytest.mark.parametrize("dim_count", [3, 4, 5])
def test_section_synthesis_matrix_dimension_count_valid(dim_count: int) -> None:
    """Verify SectionSynthesisMatrix accepts 3, 4, or 5 dimensions."""
    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(dim_count)
    ]
    matrix = SectionSynthesisMatrix(
        matrix_id=f"m-{dim_count}",
        section_id="sec-1",
        section_title="Title",
        narrative_theme="Theme",
        dimensions=dims,
        assigned_dois=["10.1/1"],
        cell_data={},
        markdown_path="path.md",
    )
    assert len(matrix.dimensions) == dim_count


def test_section_synthesis_matrix_empty_assigned_dois_rejected() -> None:
    """Verify SectionSynthesisMatrix requires at least 1 assigned DOI."""
    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(3)
    ]
    with pytest.raises(ValidationError):
        SectionSynthesisMatrix(
            matrix_id="m-1",
            section_id="sec-1",
            section_title="Title",
            narrative_theme="Theme",
            dimensions=dims,
            assigned_dois=[],  # min_length=1 violation
            cell_data={},
            markdown_path="path.md",
        )


def test_generate_matrix_output_paper_count_boundary() -> None:
    """Verify GenerateSectionSynthesisMatrixOutput paper_count is >= 1."""
    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(3)
    ]
    with pytest.raises(ValidationError):
        GenerateSectionSynthesisMatrixOutput(
            matrix_id="m-1",
            section_id="sec-1",
            dimensions=dims,
            paper_count=0,  # ge=1 violation
            markdown_path="path.md",
        )


@pytest.mark.parametrize(
    "unicode_citekey",
    [
        r"\cite{doi_10.1145/3292500_äöü}",  # German umlauts
        r"\cite{doi_10.1145/3292500_漢字}",  # CJK ideographs
        r"\cite{doi_10.1145/3292500_🚀}",  # Emoji
        r"\cite{doi_10.1145/3292500_\u200b}",  # Zero-width space
        r"\cite{doi_10.1145/3292500_ñ}",  # Spanish accent
    ],
)
def test_cell_evidence_extract_unicode_citekeys_rejected(unicode_citekey: str) -> None:
    """Verify non-ASCII / Unicode citekeys are rejected to guarantee LaTeX compilation."""
    with pytest.raises(ValidationError):
        CellEvidenceExtract(
            evidence_text="Sample text",
            citekey=unicode_citekey,
        )


def test_section_synthesis_matrix_nested_cell_validation() -> None:
    """Verify SectionSynthesisMatrix validates nested CellEvidenceExtract models recursively."""
    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(3)
    ]
    # Invalid citekey inside nested dict
    invalid_cell_data = {
        "10.1145/1": {
            "d0": {
                "evidence_text": "Evidence",
                "citekey": "invalid_no_backslash",
            }
        }
    }
    with pytest.raises(ValidationError):
        SectionSynthesisMatrix(
            matrix_id="m-1",
            section_id="sec-1",
            section_title="Title",
            narrative_theme="Theme",
            dimensions=dims,
            assigned_dois=["10.1/1"],
            cell_data=invalid_cell_data,  # type: ignore[arg-type]
            markdown_path="path.md",
        )


@pytest.mark.asyncio
async def test_neo4j_schema_ddl_error_resilience() -> None:
    """Verify _run_ddl_query catches and safely logs DB exceptions without crashing."""
    from unittest.mock import AsyncMock
    from core.db.neo4j_service import Neo4jService
    from core.db.neo4j_schema import _run_ddl_query

    mock_neo4j = AsyncMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(side_effect=Exception("Constraint already exists"))

    # Should not raise exception
    await _run_ddl_query(mock_neo4j, "CREATE CONSTRAINT fake IF NOT EXISTS ...")
    mock_neo4j.execute_write.assert_awaited_once()


# ============================================================================
# 5. ERROR TAXONOMY & STATUS CODE TESTS
# ============================================================================



def test_all_enhancement_errors_status_codes_and_payloads() -> None:
    """Verify all custom exceptions correctly serialize and map HTTP status codes."""
    cases: list[tuple[EnhancementToolError, str, int]] = [
        (MultiHopUnauthorizedError("FR-015 denied"), "MULTIHOP_UNAUTHORIZED", 403),
        (UnresolvableIdentifierError("10.unknown/1"), "UNRESOLVABLE_IDENTIFIER", 404),
        (TitleConfirmationRequiredError("Title"), "CONFIRMATION_REQUIRED", 400),
        (DuplicatePaperError("10.1/dup"), "DUPLICATE_PAPER", 409),
        (CoverageEvaluationError("rq-1", "timeout"), "COVERAGE_EVALUATION_FAILED", 500),
        (MatrixGenerationError("sec-1", "llm failed"), "MATRIX_GENERATION_FAILED", 500),
        (CitationHallucinationError("10.1/fake", "sec-1"), "CITATION_HALLUCINATION", 422),
        (EnhancementToolError("generic error"), "ENHANCEMENT_TOOL_ERROR", 500),
    ]

    for err, expected_code, expected_status in cases:
        assert err.error_code == expected_code
        assert err.http_status_code == expected_status
        assert get_http_status_code(err) == expected_status
        d = err.to_dict()
        assert d["error_code"] == expected_code
        assert d["http_status_code"] == expected_status
        assert "message" in d


def test_get_http_status_code_fallback() -> None:
    """Verify get_http_status_code returns fallback when unmapped subclass is passed."""
    class CustomNewError(EnhancementToolError):
        pass

    err = CustomNewError("custom")
    assert get_http_status_code(err) == 500


# ============================================================================
# 6. NEO4J SCHEMA DEFINITION INTEGRITY
# ============================================================================


def test_neo4j_schema_constraints_and_indexes_validity() -> None:
    """Verify Neo4j schema definitions contain exact required clauses."""
    # Assert all constraints are non-empty strings starting with CREATE CONSTRAINT
    for constraint in UNIQUENESS_CONSTRAINTS:
        assert constraint.startswith("CREATE CONSTRAINT")
        assert "IS UNIQUE" in constraint

    # Assert all composite indexes start with CREATE INDEX
    for index in COMPOSITE_INDEXES:
        assert index.startswith("CREATE INDEX")
        assert " ON " in index

    # Assert vector indexes configuration
    assert len(VECTOR_INDEXES) == 3
    for name, label, prop in VECTOR_INDEXES:
        assert name in ("paper_embeddings", "question_embeddings", "claim_embeddings")
        assert label in ("Paper", "ResearchQuestion", "Claim")
        assert prop.endswith(".embedding")
