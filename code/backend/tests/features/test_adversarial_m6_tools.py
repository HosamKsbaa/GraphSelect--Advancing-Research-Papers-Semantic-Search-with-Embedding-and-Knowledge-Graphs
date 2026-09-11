"""Adversarial stress-testing suite for Google ADK Enhancement Tools (Milestone M6).

Challenges ADK tool wrappers against adversarial conditions:
1. Unauthorized triggers and FR-015 strict necessity gating (HTTP 403).
2. Malformed inputs, missing identifiers, and unexpected payload types.
3. Missing service registries, ToolContext resolution, and graceful fallback.
4. Handling of CitationHallucinationError (HTTP 422) and ungrounded DOIs.
5. Suspension event payload attachment on terminal pause vs other states.

Complies strictly with Constitution v2.2.1:
- C7: Complete static typing.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import ValidationError
from google.adk.events import RequestInput

from agents.tools.autonomous_enhancement_tools import (
    _resolve_ingestion_service,
    _resolve_matrix_service,
    _resolve_remediation_service,
    _resolve_svpl_service,
    confirm_title_ingestion_tool,
    generate_section_synthesis_matrix_tool,
    ingest_user_paper_tool,
    run_autonomous_gap_remediation_tool,
    svpl_multi_hop_discovery_tool,
)
from core.errors.enhancement_errors import (
    CitationHallucinationError,
    DuplicatePaperError,
    MultiHopUnauthorizedError,
    UnresolvableIdentifierError,
    get_http_status_code,
)
from features.drafting.matrix_models import (
    AnalyticalDimension,
    GenerateSectionSynthesisMatrixOutput,
)
from features.drafting.matrix_service import MatrixService
from features.gap_analysis.models import (
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationOutput,
)
from features.ingestion.models import ConfirmTitleIngestionOutput, IngestUserPaperOutput
from features.ranking.svpl_models import (
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopBridgePathway,
)


def _make_dummy_tool_context(attr_name: str, svc: Any) -> Any:
    """Create a mock ToolContext with an embedded service registry."""
    tc = MagicMock()
    reg = MagicMock()
    setattr(reg, attr_name, svc)
    tc.service_registry = reg
    return tc


def _make_sample_dimensions() -> list[AnalyticalDimension]:
    """Build sample list of 3 AnalyticalDimension objects."""
    return [
        AnalyticalDimension(dimension_id=f"dim{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(1, 4)
    ]


# ===========================================================================
# 1. SVPL Multi-Hop Adversarial & Unauthorized Triggers (FR-015 / HTTP 403)
# ===========================================================================

@pytest.mark.asyncio
async def test_svpl_unauthorized_routine_crawl_reason() -> None:
    """Verify routine_crawl trigger raises MultiHopUnauthorizedError (HTTP 403)."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="routine_crawl",
        )
    assert exc_info.value.http_status_code == 403
    assert exc_info.value.error_code == "MULTIHOP_UNAUTHORIZED"
    assert "MULTIHOP_UNAUTHORIZED" in exc_info.value.message


@pytest.mark.asyncio
async def test_svpl_unauthorized_arbitrary_string_reason() -> None:
    """Verify unparseable trigger reason raises MultiHopUnauthorizedError."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="unsupported_quantum_heuristic",
        )
    assert exc_info.value.http_status_code == 403
    assert exc_info.value.error_code == "MULTIHOP_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_svpl_unauthorized_non_string_payload() -> None:
    """Verify non-string trigger reason type raises MultiHopUnauthorizedError."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason=12345,  # type: ignore[arg-type]
        )
    assert exc_info.value.http_status_code == 403


@pytest.mark.asyncio
async def test_svpl_unauthorized_gap_with_single_candidate() -> None:
    """Verify empty_gap_remediation fails when candidate_count is 1."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="empty_gap_remediation", candidate_count=1,
        )
    assert exc_info.value.http_status_code == 403
    assert "N=1" in exc_info.value.message


@pytest.mark.asyncio
async def test_svpl_unauthorized_gap_with_multiple_candidates() -> None:
    """Verify empty_gap_remediation fails when candidate_count > 0."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="empty_gap_remediation", candidate_count=5,
        )
    assert exc_info.value.http_status_code == 403
    assert "N=5" in exc_info.value.message


@pytest.mark.asyncio
async def test_svpl_unauthorized_token_explicit_flag() -> None:
    """Verify explicit is_authorized=False flag blocks invocation."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="explicit_user_directive",
            is_authorized=False,
        )
    assert exc_info.value.http_status_code == 403
    assert "denied" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_svpl_unauthorized_revoked_token_status_code() -> None:
    """Verify revoked authorization token raises MultiHopUnauthorizedError."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="explicit_user_directive",
            authorization_token="revoked",
        )
    assert exc_info.value.http_status_code == 403
    assert exc_info.value.to_dict()["http_status_code"] == 403


@pytest.mark.asyncio
async def test_svpl_authorized_zero_candidates_gap() -> None:
    """Verify empty_gap_remediation succeeds when candidate_count is 0."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=None)
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/src", target_doi="10.1000/tgt",
        trigger_reason="empty_gap_remediation", candidate_count=0,
        service=mock_svc,
    )
    assert res["status"] == "no_path_found"
    assert res["confidence"] == 0.0


@pytest.mark.asyncio
async def test_svpl_authorized_explicit_user_directive() -> None:
    """Verify explicit user directive authorizes multi-hop discovery."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=MultiHopBridgePathway(
        pathway_id="p-1", source_doi="10.1000/s", target_doi="10.1000/t",
        intermediate_nodes=[BridgeNodeSummary(openalex_id="W1", doi="10.1000/m", title="Mid")],
        mechanism=BridgeMechanism.DIRECTED_2HOP, discovered_layer=1, confidence=0.9, hop_distance=2,
    ))
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/s", target_doi="10.1000/t",
        trigger_reason="explicit_user_directive", candidate_count=3,
        service=mock_svc,
    )
    assert res["status"] == "success"
    assert res["pathway_id"] == "p-1"


# ===========================================================================
# 2. Section Synthesis Matrix & Citation Hallucination (HTTP 422)
# ===========================================================================

@pytest.mark.asyncio
async def test_matrix_ungrounded_doi_raises_hallucination_422() -> None:
    """Verify ungrounded DOI raises CitationHallucinationError (HTTP 422)."""
    mock_svc = MagicMock()
    mock_svc.generate_section_matrix = AsyncMock(
        side_effect=CitationHallucinationError(doi="10.9999/phantom", section_id="sec_01")
    )
    with pytest.raises(CitationHallucinationError) as exc_info:
        await generate_section_synthesis_matrix_tool(
            section_id="sec_01", project_id="p1", assigned_dois=["10.9999/phantom"],
            service=mock_svc,
        )
    assert exc_info.value.http_status_code == 422
    assert exc_info.value.error_code == "CITATION_HALLUCINATION"
    assert exc_info.value.doi == "10.9999/phantom"
    assert exc_info.value.section_id == "sec_01"


def test_matrix_citation_hallucination_error_properties() -> None:
    """Verify CitationHallucinationError structure and HTTP mapping."""
    err = CitationHallucinationError("10.1100/unverified", "sec_methods")
    assert err.http_status_code == 422
    assert err.error_code == "CITATION_HALLUCINATION"
    assert get_http_status_code(err) == 422
    d = err.to_dict()
    assert d["http_status_code"] == 422
    assert d["error_code"] == "CITATION_HALLUCINATION"
    assert "10.1100/unverified" in d["message"]


@pytest.mark.asyncio
async def test_matrix_integration_unindexed_doi_raises_hallucination() -> None:
    """Verify real MatrixService raises CitationHallucinationError when DOI missing in Neo4j."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"doi": "10.1000/grounded", "title": "Grounded Paper", "abstract": "Some abstract."}
    ])
    matrix_svc = MatrixService(neo4j=mock_neo4j)
    with pytest.raises(CitationHallucinationError) as exc_info:
        await generate_section_synthesis_matrix_tool(
            section_id="sec_03", project_id="p1",
            assigned_dois=["10.1000/grounded", "10.1000/missing"],
            service=matrix_svc,
        )
    assert exc_info.value.http_status_code == 422
    assert exc_info.value.doi == "10.1000/missing"


@pytest.mark.asyncio
async def test_matrix_tool_missing_section_id_raises_validation_error() -> None:
    """Verify None section_id raises Pydantic ValidationError."""
    mock_svc = MagicMock()
    with pytest.raises(ValidationError):
        await generate_section_synthesis_matrix_tool(
            section_id=None, project_id="p1", service=mock_svc,  # type: ignore[arg-type]
        )


# ===========================================================================
# 3. Gap Remediation Input Validation & Suspension Event Attachment
# ===========================================================================

@pytest.mark.asyncio
async def test_gap_remediation_invalid_mode_raises_value_error() -> None:
    """Verify invalid execution mode raises ValueError."""
    mock_svc = MagicMock()
    with pytest.raises(ValueError):
        await run_autonomous_gap_remediation_tool(
            rq_id="rq-1", project_id="p1", mode="invalid_unsupported_mode", service=mock_svc,
        )


@pytest.mark.asyncio
async def test_gap_remediation_max_iterations_zero_raises_validation_error() -> None:
    """Verify max_iterations=0 violates ge=1 and raises ValidationError."""
    mock_svc = MagicMock()
    with pytest.raises(ValidationError):
        await run_autonomous_gap_remediation_tool(
            rq_id="rq-1", project_id="p1", max_iterations=0, service=mock_svc,
        )


@pytest.mark.asyncio
async def test_gap_remediation_max_iterations_exceeded_raises_validation_error() -> None:
    """Verify max_iterations=4 violates le=3 and raises ValidationError."""
    mock_svc = MagicMock()
    with pytest.raises(ValidationError):
        await run_autonomous_gap_remediation_tool(
            rq_id="rq-1", project_id="p1", max_iterations=4, service=mock_svc,
        )


@pytest.mark.asyncio
async def test_gap_remediation_suspension_event_payload_structure() -> None:
    """Verify RequestInput suspension event attaches on paused_awaiting_input."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.MAX_ITERATIONS_PAUSED, rq_id="rq-susp-1",
        iterations_executed=3, initial_coverage=0.25, final_coverage=0.48,
        papers_ingested=[], mode=RemediationMode.EXPLORATION,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-susp-1", project_id="proj-susp", mode="exploration", service=mock_svc,
    )
    assert res["status"] == "paused_awaiting_input"
    assert "suspension_event" in res
    event = res["suspension_event"]
    assert isinstance(event, RequestInput)
    assert event.payload == {"rq_id": "rq-susp-1", "project_id": "proj-susp", "coverage": 0.48}
    assert event.message is not None
    assert "rq-susp-1" in event.message


@pytest.mark.asyncio
async def test_gap_remediation_no_suspension_when_converged() -> None:
    """Verify suspension event is omitted when remediation loop converges."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.CONVERGED, rq_id="rq-conv",
        iterations_executed=2, initial_coverage=0.5, final_coverage=0.85,
        papers_ingested=["10.1000/p1"], mode=RemediationMode.TARGETED,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-conv", project_id="proj-conv", mode="targeted", service=mock_svc,
    )
    assert res["status"] == "converged"
    assert "suspension_event" not in res


@pytest.mark.asyncio
async def test_gap_remediation_no_suspension_when_open_frontier() -> None:
    """Verify suspension event is omitted when marked as Open Research Frontier."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.OPEN_RESEARCH_FRONTIER, rq_id="rq-front",
        iterations_executed=3, initial_coverage=0.2, final_coverage=0.2,
        papers_ingested=[], mode=RemediationMode.TARGETED, is_open_frontier=True,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-front", project_id="proj-front", mode="targeted", service=mock_svc,
    )
    assert res["status"] == "open_research_frontier"
    assert "suspension_event" not in res


# ===========================================================================
# 4. Service Registry Resolution vs Production Fallback
# ===========================================================================

@pytest.mark.asyncio
async def test_tool_context_service_registry_resolution_ingestion() -> None:
    """Verify IngestionService resolves from ToolContext.service_registry."""
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="success", doi="10.1145/resolved_via_tc",
    ))
    tc = _make_dummy_tool_context("ingestion_service", mock_svc)
    res = await ingest_user_paper_tool(
        raw_input="10.1145/resolved_via_tc", project_id="p-tc", tool_context=tc,
    )
    assert res["status"] == "success"
    assert res["doi"] == "10.1145/resolved_via_tc"
    mock_svc.ingest_paper.assert_called_once()


@pytest.mark.asyncio
async def test_tool_context_service_registry_resolution_svpl() -> None:
    """Verify SVPLService resolves from ToolContext.service_registry."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=None)
    tc = _make_dummy_tool_context("svpl_service", mock_svc)
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/s", target_doi="10.1000/t",
        trigger_reason="explicit_user_directive", tool_context=tc,
    )
    assert res["status"] == "no_path_found"
    mock_svc.find_bridge_pathway.assert_called_once()


@pytest.mark.asyncio
async def test_tool_context_service_registry_resolution_remediation() -> None:
    """Verify RemediationService resolves from ToolContext.service_registry."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.CONVERGED, rq_id="rq-tc",
        iterations_executed=1, initial_coverage=0.6, final_coverage=0.8,
        papers_ingested=[], mode=RemediationMode.TARGETED,
    ))
    tc = _make_dummy_tool_context("remediation_service", mock_svc)
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-tc", project_id="p-tc", mode="targeted", tool_context=tc,
    )
    assert res["status"] == "converged"
    mock_svc.run_remediation_loop.assert_called_once()


@pytest.mark.asyncio
async def test_tool_context_service_registry_resolution_matrix() -> None:
    """Verify MatrixService resolves from ToolContext.service_registry."""
    mock_svc = MagicMock()
    mock_svc.generate_section_matrix = AsyncMock(return_value=GenerateSectionSynthesisMatrixOutput(
        status="success", matrix_id="mat-tc", section_id="sec_tc",
        dimensions=_make_sample_dimensions(), paper_count=1,
        verified_dois=["10.1000/tc"], markdown_path="path/to/matrix.md",
    ))
    tc = _make_dummy_tool_context("matrix_service", mock_svc)
    res = await generate_section_synthesis_matrix_tool(
        section_id="sec_tc", project_id="p-tc", tool_context=tc,
    )
    assert res["matrix_id"] == "mat-tc"
    mock_svc.generate_section_matrix.assert_called_once()


def test_fallback_service_resolution_when_registry_uninitialized() -> None:
    """Verify fallback instantiates service instances cleanly when registry uninitialized."""
    ingest_svc = _resolve_ingestion_service()
    assert ingest_svc is not None
    assert hasattr(ingest_svc, "ingest_paper")
    svpl_svc = _resolve_svpl_service()
    assert svpl_svc is not None
    assert hasattr(svpl_svc, "find_bridge_pathway")
    rem_svc = _resolve_remediation_service()
    assert rem_svc is not None
    assert hasattr(rem_svc, "run_remediation_loop")
    mat_svc = _resolve_matrix_service()
    assert mat_svc is not None
    assert hasattr(mat_svc, "generate_section_matrix")


# ===========================================================================
# 5. Ingestion & Confirmation Adversarial Edge Cases
# ===========================================================================

@pytest.mark.asyncio
async def test_ingest_tool_propagates_unresolvable_identifier_404() -> None:
    """Verify unresolvable identifier propagates 404 UnresolvableIdentifierError."""
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(side_effect=UnresolvableIdentifierError("10.9999/unknown"))
    with pytest.raises(UnresolvableIdentifierError) as exc_info:
        await ingest_user_paper_tool(
            raw_input="10.9999/unknown", project_id="p1", service=mock_svc,
        )
    assert exc_info.value.http_status_code == 404
    assert exc_info.value.error_code == "UNRESOLVABLE_IDENTIFIER"


@pytest.mark.asyncio
async def test_ingest_tool_propagates_duplicate_paper_409() -> None:
    """Verify duplicate paper error propagates 409 DuplicatePaperError."""
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(side_effect=DuplicatePaperError("10.1000/already_exists"))
    with pytest.raises(DuplicatePaperError) as exc_info:
        await ingest_user_paper_tool(
            raw_input="10.1000/already_exists", project_id="p1", service=mock_svc,
        )
    assert exc_info.value.http_status_code == 409
    assert exc_info.value.error_code == "DUPLICATE_PAPER"


@pytest.mark.asyncio
async def test_confirm_title_tool_missing_ids_graceful_fallback() -> None:
    """Verify missing resolved IDs fall back gracefully without unhandled exceptions."""
    mock_svc = MagicMock()
    mock_svc.confirm_title_chip = AsyncMock(return_value=ConfirmTitleIngestionOutput(
        status="confirmed", doi="10.1000/fallback", openalex_id="W_fallback_1",
        title="Title for fallback_1", citation_links_created=1, can_expand_deeply=False,
    ))
    res = await confirm_title_ingestion_tool(
        chip_id="fallback_1", project_id="p1", confirmed=True,
        resolved_openalex_id="", resolved_title="", service=mock_svc,
    )
    assert res["status"] == "confirmed"
    mock_svc.confirm_title_chip.assert_called_once()
    called_inp = mock_svc.confirm_title_chip.call_args[0][0]
    assert called_inp.resolved_openalex_id == "W_fallback_1"
    assert called_inp.resolved_title == "Title for fallback_1"


@pytest.mark.asyncio
async def test_ingest_tool_missing_project_id_raises_validation_error() -> None:
    """Verify None project_id raises Pydantic ValidationError."""
    mock_svc = MagicMock()
    with pytest.raises(ValidationError):
        await ingest_user_paper_tool(
            raw_input="10.1000/test", project_id=None, service=mock_svc,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_confirm_title_tool_missing_project_id_raises_validation_error() -> None:
    """Verify None project_id in title confirmation raises ValidationError."""
    mock_svc = MagicMock()
    with pytest.raises(ValidationError):
        await confirm_title_ingestion_tool(
            chip_id="chip-1", project_id=None, service=mock_svc,  # type: ignore[arg-type]
        )
