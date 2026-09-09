"""Comprehensive Unit Tests for Feature 007 Foundation Models, Errors & Schema (M1).

Validates:
- Ingestion Pydantic v2 domain models and contracts.
- SVPL Multi-Hop Pydantic v2 models, enums, and bounds.
- Gap Analysis Pydantic v2 models, iteration bounds, and terminal statuses.
- Section Synthesis Matrix models, dimension bounds (3-5), and LaTeX citekey regex.
- Enhancement error taxonomy, inheritance, and HTTP status code mappings.
- Neo4j schema uniqueness constraints and performance indexes.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError

from core.db.neo4j_schema import (
    COMPOSITE_INDEXES,
    UNIQUENESS_CONSTRAINTS,
    VECTOR_INDEXES,
    apply_composite_indexes,
    apply_constraints,
    initialize_schema,
)
from core.db.neo4j_service import Neo4jService
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
# 1. Ingestion Models Tests
# ============================================================================


def test_ingestion_enums() -> None:
    """Validate IngestionSource and IdentifierType enum values."""
    assert IngestionSource.SEED.value == "seed"
    assert IngestionSource.SNOWBALL.value == "snowball"
    assert IngestionSource.USER_CONTEXT.value == "user_context"
    assert IngestionSource.GAP_REMEDIATION.value == "gap_remediation"
    assert IngestionSource.MULTI_HOP_BRIDGE.value == "multi_hop_bridge"

    assert IdentifierType.DOI.value == "doi"
    assert IdentifierType.ARXIV.value == "arxiv"
    assert IdentifierType.URL.value == "url"
    assert IdentifierType.TITLE.value == "title"


def test_title_confirmation_chip_valid() -> None:
    """Validate TitleConfirmationChip creation and serialization."""
    chip = TitleConfirmationChip(
        chip_id="chip-12345",
        extracted_title="GraphRAG: Unlocking LLM Discovery",
        resolved_openalex_id="W1234567890",
        resolved_doi="10.1145/3292500",
        resolved_title="GraphRAG: Unlocking LLM Discovery on Graphs",
        similarity_score=0.94,
    )
    assert chip.status == "pending"
    assert chip.similarity_score == 0.94
    data = chip.model_dump()
    assert data["chip_id"] == "chip-12345"
    assert data["similarity_score"] == 0.94

    # Round trip deserialization
    reconstructed = TitleConfirmationChip.model_validate(data)
    assert reconstructed.chip_id == chip.chip_id
    assert reconstructed.similarity_score == chip.similarity_score


def test_title_confirmation_chip_similarity_bounds() -> None:
    """Validate TitleConfirmationChip rejects similarity scores outside [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-err-1",
            extracted_title="Sample Title",
            resolved_openalex_id="W123",
            resolved_title="Sample Official Title",
            similarity_score=1.05,
        )

    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-err-2",
            extracted_title="Sample Title",
            resolved_openalex_id="W123",
            resolved_title="Sample Official Title",
            similarity_score=-0.01,
        )


def test_title_confirmation_chip_short_title() -> None:
    """Validate TitleConfirmationChip rejects extracted titles shorter than 3 chars."""
    with pytest.raises(ValidationError):
        TitleConfirmationChip(
            chip_id="chip-err-3",
            extracted_title="ab",
            resolved_openalex_id="W123",
            resolved_title="Official Title",
            similarity_score=0.95,
        )


@pytest.mark.parametrize(
    ("input_doi", "expected_normalized"),
    [
        ("10.1145/3292500", "10.1145/3292500"),
        ("https://doi.org/10.1145/3292500", "10.1145/3292500"),
        ("http://doi.org/10.1145/3292500", "10.1145/3292500"),
        ("https://dx.doi.org/10.1145/3292500", "10.1145/3292500"),
        ("  10.1145/3292500  ", "10.1145/3292500"),
        ("10.1145/ABC_DEF", "10.1145/abc_def"),
    ],
)
def test_user_ingested_paper_doi_normalization(input_doi: str, expected_normalized: str) -> None:
    """Verify normalize_doi handles URLs, whitespace, and case normalization."""
    paper = UserIngestedPaper(
        raw_identifier=input_doi,
        doi=input_doi,
        title="Test Ingested Paper",
    )
    assert paper.doi == expected_normalized


def test_user_ingested_paper_invalid_doi() -> None:
    """Verify invalid DOI prefix raises ValidationError."""
    with pytest.raises(ValidationError):
        UserIngestedPaper(
            raw_identifier="not_a_doi",
            doi="20.1145/invalid",
            title="Invalid Paper",
        )


def test_user_ingested_paper_defaults_and_serialization() -> None:
    """Verify defaults, embedding handling, and JSON serialization."""
    paper = UserIngestedPaper(
        raw_identifier="10.1145/3292500",
        doi="10.1145/3292500",
        title="Valid Paper",
        authors=["Author One", "Author Two"],
        year=2024,
        abstract="A groundbreaking paper.",
        embedding=[0.05] * 768,
    )
    assert paper.is_stub is False
    assert paper.is_bridge is False
    assert paper.can_expand_deeply is False
    assert paper.is_retracted is False
    assert paper.ingestion_source == IngestionSource.USER_CONTEXT
    assert paper.embedding is not None
    assert len(paper.embedding) == 768

    json_str = paper.model_dump_json()
    reconstructed = UserIngestedPaper.model_validate_json(json_str)
    assert reconstructed.doi == paper.doi
    assert reconstructed.year == 2024
    assert reconstructed.embedding == paper.embedding


def test_ingest_paper_input_alias_synchronization() -> None:
    """Verify identifier and raw_input field synchronization in IngestUserPaperInput."""
    # Supplied with raw_input only
    inp1 = IngestUserPaperInput(
        raw_input="10.1145/3292500",
        project_id="proj-1",
        run_id="run-1",
    )
    assert inp1.identifier == "10.1145/3292500"
    assert inp1.raw_input == "10.1145/3292500"

    # Supplied with identifier only
    inp2 = IngestUserPaperInput(
        identifier="10.1145/3292500",
        project_id="proj-1",
        run_id="run-1",
    )
    assert inp2.identifier == "10.1145/3292500"
    assert inp2.raw_input == "10.1145/3292500"


def test_ingest_paper_output_structure() -> None:
    """Verify IngestUserPaperOutput serialization with optional chip."""
    chip = TitleConfirmationChip(
        chip_id="chip-1",
        extracted_title="Test Title",
        resolved_openalex_id="W1",
        resolved_title="Test Title Official",
        similarity_score=0.92,
    )
    out = IngestUserPaperOutput(
        status="pending_confirmation",
        doi=None,
        title="Test Title Official",
        confirmation_chip=chip,
    )
    assert out.status == "pending_confirmation"
    assert out.doi is None
    assert out.confirmation_chip is not None
    assert out.confirmation_chip.similarity_score == 0.92


def test_confirm_title_input_output() -> None:
    """Verify ConfirmTitleIngestion contracts."""
    inp = ConfirmTitleIngestionInput(
        chip_id="chip-01",
        project_id="proj-01",
        confirmed=True,
        resolved_openalex_id="W12345",
        resolved_doi="10.1145/3292500",
        resolved_title="Paper Title",
        run_id="run-01",
    )
    assert inp.confirmed is True

    out = ConfirmTitleIngestionOutput(
        status="confirmed",
        doi="10.1145/3292500",
        openalex_id="W12345",
        title="Paper Title",
        citation_links_created=4,
        can_expand_deeply=True,
    )
    assert out.status == "confirmed"
    assert out.citation_links_created == 4
    assert out.can_expand_deeply is True


# ============================================================================
# 2. SVPL Multi-Hop Models Tests
# ============================================================================


def test_bridge_mechanism_and_trigger_enums() -> None:
    """Validate BridgeMechanism and MultiHopTriggerReason enums."""
    assert BridgeMechanism.DIRECTED_2HOP.value == "directed_2hop"
    assert BridgeMechanism.REVERSE_DIRECTED_2HOP.value == "reverse_directed_2hop"
    assert BridgeMechanism.BIBLIOGRAPHIC_COUPLING.value == "bibliographic_coupling"
    assert BridgeMechanism.CO_CITATION.value == "co_citation"
    assert BridgeMechanism.PIPE_DISJUNCTIVE_3HOP.value == "pipe_disjunctive_3hop"
    assert BridgeMechanism.STEINER_BEAM_3HOP.value == "steiner_beam_3hop"

    assert MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE.value == "explicit_user_directive"
    assert MultiHopTriggerReason.EMPTY_GAP_REMEDIATION.value == "empty_gap_remediation"


def test_multihop_authorization_validation() -> None:
    """Verify MultiHopAuthorization enforces min_length=10 on context_description."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
        requester="Researcher-User",
        context_description="Targeted literature gap requires bridge",
    )
    assert auth.is_authorized is True

    with pytest.raises(ValidationError):
        MultiHopAuthorization(
            trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
            requester="Researcher-User",
            context_description="too short",
        )


def test_bridge_hop_candidate_bounds() -> None:
    """Verify BridgeHopCandidate field bounds."""
    cand = BridgeHopCandidate(
        openalex_id="W987654321",
        doi="10.1145/9999999",
        title="Intermediate Bridge Paper",
        hop_level=2,
        cosine_similarity=0.82,
        pagerank_score=0.015,
        adaptive_threshold_tau=0.74,
    )
    assert cand.hop_level == 2
    assert cand.is_pruned is False

    # hop_level out of bounds (<1 or >3)
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="T",
            hop_level=0,
            cosine_similarity=0.5,
            adaptive_threshold_tau=0.5,
        )
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="T",
            hop_level=4,
            cosine_similarity=0.5,
            adaptive_threshold_tau=0.5,
        )

    # cosine_similarity out of bounds ([-1.0, 1.0])
    with pytest.raises(ValidationError):
        BridgeHopCandidate(
            openalex_id="W1",
            title="T",
            hop_level=1,
            cosine_similarity=1.1,
            adaptive_threshold_tau=0.5,
        )


def test_multihop_bridge_pathway_serialization() -> None:
    """Verify MultiHopBridgePathway model and round trip."""
    summary = BridgeNodeSummary(
        openalex_id="W100",
        doi="10.1145/100",
        title="Mid Paper",
        year=2021,
        cited_by_count=50,
        is_stub=False,
    )
    pathway = MultiHopBridgePathway(
        pathway_id="path-uuid-1",
        source_doi="10.1145/1",
        target_doi="10.1145/2",
        intermediate_nodes=[summary],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=1,
        confidence=0.88,
        hop_distance=2,
    )
    assert pathway.discovered_layer == 1
    assert len(pathway.intermediate_nodes) == 1

    dumped = pathway.model_dump()
    reconstructed = MultiHopBridgePathway.model_validate(dumped)
    assert reconstructed.pathway_id == pathway.pathway_id
    assert reconstructed.confidence == 0.88
    assert reconstructed.intermediate_nodes[0].openalex_id == "W100"


def test_svpl_tool_input_output_contracts() -> None:
    """Verify SVPLMultiHopDiscoveryInput and SVPLMultiHopDiscoveryOutput contracts."""
    inp = SVPLMultiHopDiscoveryInput(
        source_doi="10.1145/1111",
        target_doi="10.1145/2222",
        project_id="proj-svpl-1",
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        max_hops=3,
        run_id="run-svpl-1",
    )
    assert inp.max_hops == 3

    out = SVPLMultiHopDiscoveryOutput(
        status="success",
        pathway_id="path-1",
        source_doi="10.1145/1111",
        target_doi="10.1145/2222",
        hop_distance=2,
        discovered_layer=1,
        mechanism=BridgeMechanism.BIBLIOGRAPHIC_COUPLING,
        confidence=0.91,
    )
    assert out.status == "success"
    assert out.confidence == 0.91


# ============================================================================
# 3. Gap Analysis Models Tests
# ============================================================================


def test_gap_analysis_enums() -> None:
    """Validate RemediationMode and RemediationCycleStatus enums."""
    assert RemediationMode.EXPLORATION.value == "exploration"
    assert RemediationMode.REFINEMENT.value == "refinement"
    assert RemediationMode.TARGETED.value == "targeted"

    assert RemediationCycleStatus.CONVERGED.value == "converged"
    assert RemediationCycleStatus.MAX_ITERATIONS_PAUSED.value == "paused_awaiting_input"
    assert RemediationCycleStatus.OPEN_RESEARCH_FRONTIER.value == "open_research_frontier"
    assert RemediationCycleStatus.IN_PROGRESS.value == "in_progress"


def test_gap_remediation_cycle_bounds() -> None:
    """Verify GapRemediationCycle constraints and delta calculation."""
    cycle = GapRemediationCycle(
        cycle_id="cycle-01",
        iteration=2,
        target_rq_id="rq-100",
        initial_coverage=0.45,
        queries_generated=["query one", "query two"],
        retrieved_candidate_dois=["10.1145/1", "10.1145/2"],
        accepted_dois=["10.1145/1"],
        resulting_coverage=0.75,
        coverage_delta=0.30,
        status=RemediationCycleStatus.CONVERGED,
    )
    assert cycle.iteration == 2
    assert cycle.coverage_delta == 0.30
    assert cycle.status == RemediationCycleStatus.CONVERGED

    # Iteration out of bounds (>3)
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c2",
            iteration=4,
            target_rq_id="rq-1",
            initial_coverage=0.1,
            queries_generated=["q"],
            resulting_coverage=0.2,
            coverage_delta=0.1,
            status=RemediationCycleStatus.IN_PROGRESS,
        )

    # Empty queries list
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c3",
            iteration=1,
            target_rq_id="rq-1",
            initial_coverage=0.1,
            queries_generated=[],
            resulting_coverage=0.2,
            coverage_delta=0.1,
            status=RemediationCycleStatus.IN_PROGRESS,
        )

    # Candidate DOIs > 3
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c4",
            iteration=1,
            target_rq_id="rq-1",
            initial_coverage=0.1,
            queries_generated=["q"],
            retrieved_candidate_dois=["10.1/1", "10.1/2", "10.1/3", "10.1/4"],
            resulting_coverage=0.2,
            coverage_delta=0.1,
            status=RemediationCycleStatus.IN_PROGRESS,
        )


def test_gap_remediation_tool_contracts() -> None:
    """Verify RunAutonomousGapRemediationInput/Output contracts."""
    inp = RunAutonomousGapRemediationInput(
        project_id="proj-gap-1",
        rq_id="rq-gap-1",
        mode=RemediationMode.EXPLORATION,
        max_iterations=3,
        run_id="run-gap-1",
    )
    assert inp.max_iterations == 3

    out = RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.MAX_ITERATIONS_PAUSED,
        rq_id="rq-gap-1",
        iterations_executed=3,
        initial_coverage=0.35,
        final_coverage=0.55,
        papers_ingested=["10.1145/p1"],
        mode=RemediationMode.EXPLORATION,
        is_open_frontier=False,
    )
    assert out.status == RemediationCycleStatus.MAX_ITERATIONS_PAUSED
    assert out.iterations_executed == 3


# ============================================================================
# 4. Section Synthesis Matrix Models Tests
# ============================================================================


def test_analytical_dimension_creation() -> None:
    """Verify AnalyticalDimension instantiation and default values."""
    dim = AnalyticalDimension(
        dimension_id="mitigation_mechanism",
        name="Mitigation Mechanism",
        description="Core algorithmic mechanism proposed to mitigate hallucinations",
    )
    assert dim.evaluation_type == "qualitative"
    assert dim.dimension_id == "mitigation_mechanism"


@pytest.mark.parametrize(
    "valid_citekey",
    [
        r"\cite{doi_10_1145_3292500}",
        r"\cite{doi_10.1145/3292500}",
        r"\cite{doi_10-1234/test.v1}",
        r"\cite{doi_10_1016_j_knosys_2024_01}",
    ],
)
def test_cell_evidence_extract_valid_citekeys(valid_citekey: str) -> None:
    """Verify valid LaTeX citekeys match canonical regex ^\\cite{doi_[a-zA-Z0-9_\\-\\.\\/]+}$."""
    extract = CellEvidenceExtract(
        evidence_text="Proposes graph grounding to eliminate hallucinations.",
        quantitative_metric="99.4% precision",
        citekey=valid_citekey,
        is_grounded=True,
    )
    assert extract.citekey == valid_citekey
    assert CITEKEY_PATTERN.match(valid_citekey) is not None


@pytest.mark.parametrize(
    "invalid_citekey",
    [
        "doi_10_1145_3292500",
        r"\cite{}",
        r"\cite{10.1145/3292500}",
        r"\cite{doi_}",
        r"cite{doi_123}",
        r"\cite{doi_invalid spaces}",
        "plain text reference",
    ],
)
def test_cell_evidence_extract_invalid_citekeys(invalid_citekey: str) -> None:
    """Verify invalid LaTeX citekeys raise ValidationError."""
    with pytest.raises(ValidationError):
        CellEvidenceExtract(
            evidence_text="Sample evidence text",
            citekey=invalid_citekey,
        )


def test_section_synthesis_matrix_dimension_bounds() -> None:
    """Verify SectionSynthesisMatrix requires between 3 and 5 dimensions."""
    dims_2 = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(2)
    ]
    dims_3 = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(3)
    ]
    dims_5 = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(5)
    ]
    dims_6 = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(6)
    ]

    cell_data = {
        "10.1145/1": {
            "d0": CellEvidenceExtract(evidence_text="Claim", citekey=r"\cite{doi_10_1145_1}")
        }
    }

    # 2 dimensions -> Fails (min 3)
    with pytest.raises(ValidationError):
        SectionSynthesisMatrix(
            matrix_id="m1",
            section_id="sec_01",
            section_title="Sec Title",
            narrative_theme="Theme",
            dimensions=dims_2,
            assigned_dois=["10.1145/1"],
            cell_data=cell_data,
            markdown_path="stage_04_artifacts/matrices/sec_01.md",
        )

    # 6 dimensions -> Fails (max 5)
    with pytest.raises(ValidationError):
        SectionSynthesisMatrix(
            matrix_id="m2",
            section_id="sec_01",
            section_title="Sec Title",
            narrative_theme="Theme",
            dimensions=dims_6,
            assigned_dois=["10.1145/1"],
            cell_data=cell_data,
            markdown_path="stage_04_artifacts/matrices/sec_01.md",
        )

    # 3 and 5 dimensions -> Pass
    m3 = SectionSynthesisMatrix(
        matrix_id="m3",
        section_id="sec_01",
        section_title="Sec Title",
        narrative_theme="Theme",
        dimensions=dims_3,
        assigned_dois=["10.1145/1"],
        cell_data=cell_data,
        markdown_path="stage_04_artifacts/matrices/sec_01.md",
    )
    assert len(m3.dimensions) == 3

    m5 = SectionSynthesisMatrix(
        matrix_id="m5",
        section_id="sec_01",
        section_title="Sec Title",
        narrative_theme="Theme",
        dimensions=dims_5,
        assigned_dois=["10.1145/1"],
        cell_data=cell_data,
        markdown_path="stage_04_artifacts/matrices/sec_01.md",
    )
    assert len(m5.dimensions) == 5


def test_section_synthesis_matrix_serialization() -> None:
    """Verify SectionSynthesisMatrix serialization and deserialization."""
    dims = [
        AnalyticalDimension(dimension_id=f"dim_{i}", name=f"Dimension {i}", description=f"Desc {i}")
        for i in range(3)
    ]
    extract = CellEvidenceExtract(
        evidence_text="State-of-the-art multi-hop graph retrieval result",
        quantitative_metric="+32.4% Recall@10",
        citekey=r"\cite{doi_10_1145_3292500}",
        is_grounded=True,
    )
    cell_data = {"10.1145/3292500": {"dim_0": extract}}

    matrix = SectionSynthesisMatrix(
        matrix_id="matrix-uuid-1",
        section_id="sec_methodology",
        section_title="Methodological Foundations",
        narrative_theme="Comparative appraisal of graph-vector architectures",
        dimensions=dims,
        assigned_dois=["10.1145/3292500"],
        verified_dois=["10.1145/3292500"],
        cell_data=cell_data,
        markdown_path="stage_04_artifacts/matrices/sec_methodology.md",
    )

    dumped_json = matrix.model_dump_json()
    reconstructed = SectionSynthesisMatrix.model_validate_json(dumped_json)
    assert reconstructed.matrix_id == "matrix-uuid-1"
    assert reconstructed.section_id == "sec_methodology"
    assert reconstructed.cell_data["10.1145/3292500"]["dim_0"].citekey == r"\cite{doi_10_1145_3292500}"


def test_generate_matrix_contracts() -> None:
    """Verify GenerateSectionSynthesisMatrixInput and Output contracts."""
    inp = GenerateSectionSynthesisMatrixInput(
        project_id="proj-mat-1",
        section_id="sec_intro",
        section_title="Introduction",
        narrative_theme="Historical survey",
        assigned_dois=["10.1145/1", "10.1145/2"],
        run_id="run-mat-1",
    )
    assert inp.stage_index == 4
    assert len(inp.assigned_dois) == 2

    dims = [
        AnalyticalDimension(dimension_id=f"d{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(4)
    ]
    out = GenerateSectionSynthesisMatrixOutput(
        matrix_id="mat-res-1",
        section_id="sec_intro",
        dimensions=dims,
        paper_count=2,
        verified_dois=["10.1145/1", "10.1145/2"],
        markdown_path="stage_04_artifacts/matrices/sec_intro.md",
    )
    assert out.paper_count == 2
    assert len(out.dimensions) == 4


# ============================================================================
# 5. Error Taxonomy & HTTP Status Code Mappings Tests
# ============================================================================


def test_enhancement_error_hierarchy() -> None:
    """Verify all custom exceptions inherit from EnhancementToolError and Exception."""
    errors = [
        MultiHopUnauthorizedError("unauthorized"),
        UnresolvableIdentifierError("10.invalid/xxx"),
        TitleConfirmationRequiredError("Some Title"),
        DuplicatePaperError("10.1145/duplicate"),
        CoverageEvaluationError("rq-1", "reason"),
        MatrixGenerationError("sec-1", "reason"),
        CitationHallucinationError("10.hallucinated/doi", "sec-1"),
    ]

    for err in errors:
        assert isinstance(err, EnhancementToolError)
        assert isinstance(err, Exception)


def test_enhancement_error_codes_and_status_mappings() -> None:
    """Verify deterministic error codes, HTTP status codes, and serialization."""
    err_multihop = MultiHopUnauthorizedError("FR-015 violation")
    assert err_multihop.error_code == "MULTIHOP_UNAUTHORIZED"
    assert get_http_status_code(err_multihop) == 403
    assert err_multihop.to_dict()["http_status_code"] == 403

    err_unresolvable = UnresolvableIdentifierError("10.unknown/123")
    assert err_unresolvable.error_code == "UNRESOLVABLE_IDENTIFIER"
    assert get_http_status_code(err_unresolvable) == 404
    assert err_unresolvable.identifier == "10.unknown/123"

    err_chip = TitleConfirmationRequiredError("Survey on Agents")
    assert err_chip.error_code == "CONFIRMATION_REQUIRED"
    assert get_http_status_code(err_chip) == 400
    assert err_chip.title == "Survey on Agents"

    err_dup = DuplicatePaperError("10.1145/already_there")
    assert err_dup.error_code == "DUPLICATE_PAPER"
    assert get_http_status_code(err_dup) == 409
    assert err_dup.doi == "10.1145/already_there"

    err_cov = CoverageEvaluationError("rq-42", "Neo4j timeout")
    assert err_cov.error_code == "COVERAGE_EVALUATION_FAILED"
    assert get_http_status_code(err_cov) == 500
    assert err_cov.rq_id == "rq-42"

    err_mat = MatrixGenerationError("sec_04", "LLM parsing error")
    assert err_mat.error_code == "MATRIX_GENERATION_FAILED"
    assert get_http_status_code(err_mat) == 500

    err_hallucination = CitationHallucinationError("10.1234/fake", "sec_04")
    assert err_hallucination.error_code == "CITATION_HALLUCINATION"
    assert get_http_status_code(err_hallucination) == 422
    assert err_hallucination.doi == "10.1234/fake"
    assert err_hallucination.section_id == "sec_04"


def test_catch_all_via_base_exception() -> None:
    """Verify EnhancementToolError cleanly catches all specialized domain exceptions."""
    def raise_hallucination() -> None:
        raise CitationHallucinationError("10.1111/missing", "sec_methods")

    with pytest.raises(EnhancementToolError) as exc_info:
        raise_hallucination()

    assert exc_info.value.error_code == "CITATION_HALLUCINATION"
    assert get_http_status_code(exc_info.value) == 422


# ============================================================================
# 6. Neo4j Schema Definitions & Syntax Tests
# ============================================================================


def test_neo4j_schema_constraints_presence() -> None:
    """Verify required Feature 007 uniqueness constraints exist in schema list."""
    constraints_str = " ".join(UNIQUENESS_CONSTRAINTS)

    # Core required Feature 007 constraints
    assert "matrix_section_unique" in constraints_str
    assert "SectionSynthesisMatrix" in constraints_str
    assert "m.section_id IS UNIQUE" in constraints_str

    assert "section_id_unique" in constraints_str
    assert "OutlineSection" in constraints_str

    # Pre-existing core constraints must remain intact
    assert "paper_doi_unique" in constraints_str
    assert "question_id_unique" in constraints_str
    assert "project_id_unique" in constraints_str


def test_neo4j_schema_indexes_presence() -> None:
    """Verify required Feature 007 performance indexes exist in schema list."""
    indexes_str = " ".join(COMPOSITE_INDEXES)

    assert "paper_is_bridge_idx" in indexes_str
    assert "p.is_bridge" in indexes_str

    assert "paper_is_stub_idx" in indexes_str
    assert "p.is_stub" in indexes_str

    assert "paper_deep_expand_idx" in indexes_str
    assert "p.can_expand_deeply" in indexes_str

    assert "paper_is_retracted_idx" in indexes_str
    assert "p.is_retracted" in indexes_str


def test_neo4j_vector_indexes_intact() -> None:
    """Verify Matryoshka 768d vector indexes remain intact."""
    assert len(VECTOR_INDEXES) == 3
    names = {idx[0] for idx in VECTOR_INDEXES}
    assert names == {"paper_embeddings", "question_embeddings", "claim_embeddings"}


@pytest.mark.asyncio
async def test_neo4j_initialize_schema_mock() -> None:
    """Verify initialize_schema executes all constraints and indexes via execute_write."""
    mock_neo4j = AsyncMock(spec=Neo4jService)
    mock_neo4j.execute_write = AsyncMock(return_value=[])

    await initialize_schema(mock_neo4j, embedding_dimensions=768)

    total_expected = len(UNIQUENESS_CONSTRAINTS) + len(COMPOSITE_INDEXES) + len(VECTOR_INDEXES)
    assert mock_neo4j.execute_write.call_count == total_expected

    executed_queries = [call.args[0] for call in mock_neo4j.execute_write.call_args_list]
    executed_text = " ".join(executed_queries)

    assert "matrix_section_unique" in executed_text
    assert "paper_is_bridge_idx" in executed_text
    assert "paper_is_stub_idx" in executed_text
    assert "paper_deep_expand_idx" in executed_text
    assert "paper_is_retracted_idx" in executed_text
    assert "paper_embeddings" in executed_text
