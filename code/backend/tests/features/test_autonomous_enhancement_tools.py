"""Unit and integration tests for Google ADK Autonomous Enhancement Tools (T049 / Milestone M6).

Verifies all 5 ADK tools exposed in agents/tools/autonomous_enhancement_tools.py:
1. ingest_user_paper_tool
2. confirm_title_ingestion_tool
3. svpl_multi_hop_discovery_tool
4. run_autonomous_gap_remediation_tool
5. generate_section_synthesis_matrix_tool

Conforms to ADR-001, Constitution v2.2.1 (C2, C5, C7, C9, A15, A28, A37, FR-015).
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from agents._service_registry import ServiceRegistry
from agents.tools.autonomous_enhancement_tools import (
    _get_registry_service,
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
    MultiHopUnauthorizedError,
    UnresolvableIdentifierError,
)
from features.drafting.matrix_models import (
    AnalyticalDimension,
    GenerateSectionSynthesisMatrixOutput,
)
from features.gap_analysis.models import (
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationOutput,
)
from features.ingestion.models import (
    ConfirmTitleIngestionOutput,
    IngestUserPaperOutput,
    TitleConfirmationChip,
)
from features.ranking.svpl_models import (
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopBridgePathway,
)


def _make_sample_chip() -> TitleConfirmationChip:
    """Build sample TitleConfirmationChip for tests."""
    return TitleConfirmationChip(
        chip_id=str(uuid.uuid4()),
        extracted_title="Attention Is All You Need",
        resolved_openalex_id="W2964313674",
        resolved_doi="10.48550/arxiv.1706.03762",
        resolved_title="Attention Is All You Need",
        similarity_score=0.96,
        status="pending",
    )


def _make_sample_pathway() -> MultiHopBridgePathway:
    """Build sample MultiHopBridgePathway for tests."""
    return MultiHopBridgePathway(
        pathway_id="pw-123",
        source_doi="10.1000/source",
        target_doi="10.1000/target",
        intermediate_nodes=[
            BridgeNodeSummary(openalex_id="W100", doi="10.1000/mid", title="Bridge Paper")
        ],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=1,
        confidence=0.92,
        hop_distance=2,
    )


def _make_sample_dimensions() -> list[AnalyticalDimension]:
    """Build sample list of AnalyticalDimension objects."""
    return [
        AnalyticalDimension(dimension_id=f"dim{i}", name=f"Dim {i}", description=f"Desc {i}")
        for i in range(1, 4)
    ]


# ---------------------------------------------------------------------------
# Ingestion Tool Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_user_paper_tool_success() -> None:
    """Verify ingest_user_paper_tool delegates to service and returns serialized dict."""
    mock_service = MagicMock()
    mock_service.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="success", doi="10.1145/3442381.3449834",
        openalex_id="W3128456789", title="Graph Neural Networks in Action",
        citation_links_created=4, can_expand_deeply=True, max_rq_relevance=0.88,
    ))
    res = await ingest_user_paper_tool(
        raw_input="10.1145/3442381.3449834", project_id="proj-test-1", service=mock_service,
    )
    assert res["status"] == "success"
    assert res["doi"] == "10.1145/3442381.3449834"
    assert res["citation_links_created"] == 4
    assert res["can_expand_deeply"] is True


@pytest.mark.asyncio
async def test_ingest_user_paper_tool_pending_title_chip() -> None:
    """Verify tool returns pending_confirmation output when free-text title is provided."""
    mock_service = MagicMock()
    mock_service.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="pending_confirmation", doi=None, confirmation_chip=_make_sample_chip(),
    ))
    res = await ingest_user_paper_tool(
        raw_input="Attention Is All You Need", project_id="proj-test-1", service=mock_service,
    )
    assert res["status"] == "pending_confirmation"
    assert res["confirmation_chip"]["similarity_score"] == 0.96


@pytest.mark.asyncio
async def test_ingest_user_paper_tool_error_propagation() -> None:
    """Verify unresolvable identifier raises UnresolvableIdentifierError."""
    mock_service = MagicMock()
    mock_service.ingest_paper = AsyncMock(side_effect=UnresolvableIdentifierError("10.9999/none"))
    with pytest.raises(UnresolvableIdentifierError):
        await ingest_user_paper_tool(
            raw_input="10.9999/none", project_id="proj-test-1", service=mock_service,
        )


# ---------------------------------------------------------------------------
# Confirm Title Tool Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_title_ingestion_tool_confirmed() -> None:
    """Verify confirm_title_ingestion_tool handles confirmed chip action."""
    mock_service = MagicMock()
    mock_service.confirm_title_chip = AsyncMock(return_value=ConfirmTitleIngestionOutput(
        status="confirmed", doi="10.48550/arxiv.1706.03762",
        openalex_id="W2964313674", title="Attention Is All You Need",
        citation_links_created=8, can_expand_deeply=True,
    ))
    res = await confirm_title_ingestion_tool(
        chip_id="chip-123", project_id="proj-test-1", confirmed=True, service=mock_service,
    )
    assert res["status"] == "confirmed"
    assert res["doi"] == "10.48550/arxiv.1706.03762"
    assert res["can_expand_deeply"] is True


@pytest.mark.asyncio
async def test_confirm_title_ingestion_tool_dismissed() -> None:
    """Verify confirm_title_ingestion_tool handles dismissed chip action."""
    mock_service = MagicMock()
    mock_service.confirm_title_chip = AsyncMock(return_value=ConfirmTitleIngestionOutput(
        status="dismissed", doi=None, openalex_id="W2964313674",
        title="Attention Is All You Need", citation_links_created=0, can_expand_deeply=False,
    ))
    res = await confirm_title_ingestion_tool(
        chip_id="chip-123", project_id="proj-test-1", confirmed=False, service=mock_service,
    )
    assert res["status"] == "dismissed"
    assert res["doi"] is None


# ---------------------------------------------------------------------------
# SVPL Multi-Hop Tool Tests & Strict Gating (FR-015)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_svpl_multi_hop_discovery_tool_success() -> None:
    """Verify authorized multi-hop discovery returns serialized pathway."""
    mock_service = MagicMock()
    mock_service.find_bridge_pathway = AsyncMock(return_value=_make_sample_pathway())
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/source", target_doi="10.1000/target",
        trigger_reason="explicit_user_directive", project_id="proj-1", service=mock_service,
    )
    assert res["status"] == "success"
    assert res["pathway_id"] == "pw-123"
    assert res["hop_distance"] == 2
    assert res["mechanism"] == "directed_2hop"
    assert len(res["intermediate_nodes"]) == 1


@pytest.mark.asyncio
async def test_svpl_multi_hop_discovery_tool_no_path_found() -> None:
    """Verify tool returns no_path_found structure when no bridge is discovered."""
    mock_service = MagicMock()
    mock_service.find_bridge_pathway = AsyncMock(return_value=None)
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/isolated_a", target_doi="10.1000/isolated_b",
        trigger_reason="explicit_user_directive", service=mock_service,
    )
    assert res["status"] == "no_path_found"
    assert res["pathway_id"] is None
    assert res["confidence"] == 0.0


@pytest.mark.asyncio
async def test_svpl_multi_hop_discovery_tool_unauthorized_trigger_raises() -> None:
    """Verify unauthorized trigger raises MultiHopUnauthorizedError per FR-015."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b", trigger_reason="routine_crawl",
        )


@pytest.mark.asyncio
async def test_svpl_multi_hop_discovery_tool_gap_with_candidates_raises() -> None:
    """Verify empty_gap_remediation raises if candidate_count > 0 (FR-015)."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="empty_gap_remediation", candidate_count=2,
        )


@pytest.mark.asyncio
async def test_svpl_multi_hop_discovery_tool_revoked_token_raises() -> None:
    """Verify revoked authorization token raises MultiHopUnauthorizedError."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/a", target_doi="10.1000/b",
            trigger_reason="explicit_user_directive", authorization_token="revoked",
        )


# ---------------------------------------------------------------------------
# Gap Remediation Tool Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gap_remediation_tool_converged() -> None:
    """Verify run_autonomous_gap_remediation_tool handles converged cycle."""
    mock_service = MagicMock()
    mock_service.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.CONVERGED, rq_id="rq-1", iterations_executed=2,
        initial_coverage=0.45, final_coverage=0.76,
        papers_ingested=["10.1000/p1", "10.1000/p2"], mode=RemediationMode.TARGETED,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-1", project_id="proj-1", mode="targeted", service=mock_service,
    )
    assert res["status"] == "converged"
    assert res["iterations_executed"] == 2
    assert res["final_coverage"] == 0.76
    assert len(res["papers_ingested"]) == 2


@pytest.mark.asyncio
async def test_gap_remediation_tool_exploration_pause_and_suspension() -> None:
    """Verify exploration mode pauses and carries ADK suspension event."""
    mock_service = MagicMock()
    mock_service.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.MAX_ITERATIONS_PAUSED, rq_id="rq-pause",
        iterations_executed=3, initial_coverage=0.30, final_coverage=0.45,
        papers_ingested=[], mode=RemediationMode.EXPLORATION,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-pause", project_id="proj-1", mode="exploration", service=mock_service,
    )
    assert res["status"] == "paused_awaiting_input"
    assert "suspension_event" in res
    assert res["suspension_event"].message is not None


@pytest.mark.asyncio
async def test_gap_remediation_tool_targeted_frontier() -> None:
    """Verify targeted mode marks open research frontier after exhausted loops."""
    mock_service = MagicMock()
    mock_service.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.OPEN_RESEARCH_FRONTIER, rq_id="rq-frontier",
        iterations_executed=3, initial_coverage=0.20, final_coverage=0.20,
        papers_ingested=[], mode=RemediationMode.TARGETED, is_open_frontier=True,
    ))
    res = await run_autonomous_gap_remediation_tool(
        rq_id="rq-frontier", project_id="proj-1", mode="targeted", service=mock_service,
    )
    assert res["status"] == "open_research_frontier"
    assert res["is_open_frontier"] is True


# ---------------------------------------------------------------------------
# Section Synthesis Matrix Tool Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_section_matrix_tool_success() -> None:
    """Verify generate_section_synthesis_matrix_tool creates matrix model."""
    mock_service = MagicMock()
    mock_service.generate_section_matrix = AsyncMock(return_value=GenerateSectionSynthesisMatrixOutput(
        status="success", matrix_id="mat-999", section_id="sec_02_methodology",
        dimensions=_make_sample_dimensions(), paper_count=2,
        verified_dois=["10.1000/p1", "10.1000/p2"],
        markdown_path="stage_04_artifacts/matrices/sec_02_methodology.md",
    ))
    res = await generate_section_synthesis_matrix_tool(
        section_id="sec_02_methodology", project_id="proj-1", service=mock_service,
    )
    assert res["status"] == "success"
    assert res["matrix_id"] == "mat-999"
    assert len(res["dimensions"]) == 3
    assert len(res["verified_dois"]) == 2


@pytest.mark.asyncio
async def test_section_matrix_tool_ungrounded_raises_citation_hallucination() -> None:
    """Verify ungrounded citation in matrix raises CitationHallucinationError (A37)."""
    mock_service = MagicMock()
    mock_service.generate_section_matrix = AsyncMock(
        side_effect=CitationHallucinationError("10.9999/hallucinated", "sec_02_methodology")
    )
    with pytest.raises(CitationHallucinationError):
        await generate_section_synthesis_matrix_tool(
            section_id="sec_02_methodology", project_id="proj-1", service=mock_service,
        )


# ---------------------------------------------------------------------------
# Default Service Resolution & Lazy Initialization Tests
# ---------------------------------------------------------------------------

def test_default_service_resolution_via_registry() -> None:
    """Verify default resolvers retrieve real non-null services from ServiceRegistry."""
    ingest_svc = _resolve_ingestion_service()
    assert ingest_svc is not None
    assert ingest_svc.neo4j is not None
    assert ingest_svc.openalex is not None

    matrix_svc = _resolve_matrix_service()
    assert matrix_svc is not None
    assert matrix_svc.neo4j is not None

    svpl_svc = _resolve_svpl_service()
    assert svpl_svc is not None
    assert svpl_svc._neo4j is not None

    rem_svc = _resolve_remediation_service()
    assert rem_svc is not None
    assert rem_svc.neo4j is not None


def test_get_registry_service_triggers_lazy_initialization() -> None:
    """Verify _get_registry_service invokes ServiceRegistryMeta lazy init."""
    neo4j = _get_registry_service("neo4j")
    assert neo4j is not None
    openalex = _get_registry_service("openalex")
    assert openalex is not None
    missing = _get_registry_service("unknown_nonexistent_service")
    assert missing is None


@pytest.mark.asyncio
async def test_tool_matrix_default_service_resolution_calls_registry() -> None:
    """Verify generate_section_synthesis_matrix_tool resolves MatrixService by default."""
    svc = _resolve_matrix_service()
    assert svc.neo4j is not None
    assert isinstance(svc.neo4j, object)

