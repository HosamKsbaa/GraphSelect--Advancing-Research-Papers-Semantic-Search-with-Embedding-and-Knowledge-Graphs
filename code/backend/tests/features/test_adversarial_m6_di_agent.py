"""Adversarial challenge and empirical verification test suite for Milestone M6.

Verifies:
1. FastAPI DI providers in core/dependencies.py (lifecycle, 503 errors, resolution, overrides).
2. Agent tool accessibility and privilege separation in SearchSnowballAgent and MethodologyArchitect.
3. End-to-end simulated agent execution flows (ingestion, title confirmation, SVPL gating, gap remediation, matrices).
4. PaperRead legacy compatibility, FastAPI response serialization, and zero-RAM invariants.

Strictly complies with Constitution v2.2.1:
- C2: Explicit dependencies
- C7: Strict static typing
- C8: Pure Neo4j SSOT, zero MySQL
- C9: Granular sub-routines strictly <= 25 lines (SRP / SLAP)
- A5: Zero RAM embedding policy
- A37: Zero citation hallucination
- FR-015: Strict necessity gating on multi-hop discovery
"""
from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from agents.stage2_acquisition.agent import (
    create_relevance_quality_auditor_agent,
    create_search_snowball_agent,
)
from agents.stage4_synthesis.agent import (
    create_methodology_architect_agent,
    create_novelty_rigor_challenger_agent,
)
from agents.tools.autonomous_enhancement_tools import (
    confirm_title_ingestion_tool,
    generate_section_synthesis_matrix_tool,
    ingest_user_paper_tool,
    run_autonomous_gap_remediation_tool,
    svpl_multi_hop_discovery_tool,
)
from core.dependencies import (
    get_ingestion_service,
    get_matrix_service,
    get_openalex_service,
    get_remediation_service,
    get_svpl_service,
)
from core.errors.enhancement_errors import (
    CitationHallucinationError,
    MultiHopUnauthorizedError,
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
from features.gap_analysis.remediation_service import RemediationService
from features.ingestion.ingestion_service import IngestionService
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
from features.ranking.svpl_service import SVPLService
from features.retrieval.models import PaperRead


# ---------------------------------------------------------------------------
# Test Helpers (strictly <= 25 lines)
# ---------------------------------------------------------------------------

def _make_test_app() -> FastAPI:
    """Build test FastAPI app with routes injecting all 4 M6 enhancement dependencies."""
    app = FastAPI()

    @app.get("/test/ingestion")
    def r_ingest(svc: IngestionService = Depends(get_ingestion_service)) -> dict[str, str]:
        return {"class": svc.__class__.__name__}

    @app.get("/test/svpl")
    def r_svpl(svc: SVPLService = Depends(get_svpl_service)) -> dict[str, str]:
        return {"class": svc.__class__.__name__}

    @app.get("/test/remediation")
    def r_rem(svc: RemediationService = Depends(get_remediation_service)) -> dict[str, str]:
        return {"class": svc.__class__.__name__}

    @app.get("/test/matrix")
    def r_mat(svc: MatrixService = Depends(get_matrix_service)) -> dict[str, str]:
        return {"class": svc.__class__.__name__}

    return app


def _make_sample_dimensions() -> list[AnalyticalDimension]:
    """Return minimal 3 analytical dimensions required for matrix output."""
    return [
        AnalyticalDimension(
            dimension_id=f"dim_{i}",
            name=f"Dimension {i}",
            description=f"Description {i}",
        )
        for i in range(1, 4)
    ]


def _make_sample_pathway() -> MultiHopBridgePathway:
    """Return sample MultiHopBridgePathway for SVPL discovery tests."""
    return MultiHopBridgePathway(
        pathway_id="pw-adv-1",
        source_doi="10.1000/source",
        target_doi="10.1000/target",
        intermediate_nodes=[
            BridgeNodeSummary(openalex_id="W123", doi="10.1000/bridge", title="Bridge Intermediate")
        ],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=1,
        confidence=0.95,
        hop_distance=2,
    )


def _make_tool_context(**services: Any) -> Any:
    """Build lightweight ToolContext stand-in containing service registry."""
    registry = MagicMock()
    for key, value in services.items():
        setattr(registry, key, value)
    ctx = MagicMock()
    ctx.service_registry = registry
    return ctx


# ---------------------------------------------------------------------------
# Section 1: FastAPI Dependency Injection Providers & Lifecycle
# ---------------------------------------------------------------------------

def test_di_app_resolves_all_four_enhancement_services() -> None:
    """Verify FastAPI DI container resolves all 4 enhancement providers with mock Neo4j."""
    app = _make_test_app()
    app.state.neo4j_service = MagicMock()
    client = TestClient(app)
    endpoints = ["/test/ingestion", "/test/svpl", "/test/remediation", "/test/matrix"]
    expected = ["IngestionService", "SVPLService", "RemediationService", "MatrixService"]
    for path, expected_cls in zip(endpoints, expected):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.json() == {"class": expected_cls}


@pytest.mark.parametrize("path", ["/test/ingestion", "/test/svpl", "/test/remediation", "/test/matrix"])
def test_di_missing_neo4j_raises_503_across_endpoints(path: str) -> None:
    """Verify HTTP 503 is returned when Neo4j is uninitialized in app.state."""
    app = _make_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(path)
    assert resp.status_code == 503
    assert resp.json() == {"detail": "Neo4j service not initialized"}


def test_di_dependency_overrides_substitution() -> None:
    """Verify FastAPI app.dependency_overrides cleanly substitutes M6 services."""
    app = _make_test_app()
    mock_ingestion = MagicMock()
    mock_ingestion.__class__.__name__ = "MockCustomIngestionService"
    app.dependency_overrides[get_ingestion_service] = lambda: mock_ingestion
    client = TestClient(app)
    resp = client.get("/test/ingestion")
    assert resp.status_code == 200
    assert resp.json() == {"class": "MockCustomIngestionService"}


@pytest.mark.asyncio
async def test_di_openalex_generator_teardown_lifecycle() -> None:
    """Verify get_openalex_service async generator closes OpenAlex client in finally block."""
    settings = MagicMock(openalex_api_key="test_key")
    log_svc = MagicMock()
    with patch("core.dependencies.OpenAlexService") as mock_cls:
        mock_inst = AsyncMock()
        mock_cls.return_value = mock_inst
        gen = get_openalex_service(settings=settings, log_service=log_svc)
        service = await anext(gen)
        assert service is mock_inst
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
        mock_inst.close.assert_awaited_once()


def test_di_direct_provider_invocations_bind_arguments() -> None:
    """Verify direct calls to DI providers bind explicitly passed sub-service instances."""
    mock_neo4j = MagicMock()
    mock_openalex = MagicMock()
    mock_gemini = MagicMock()
    ing_svc = get_ingestion_service(neo4j=mock_neo4j, openalex=mock_openalex, gemini=mock_gemini)
    svpl_svc = get_svpl_service(neo4j=mock_neo4j, openalex=mock_openalex, gemini=mock_gemini)
    rem_svc = get_remediation_service(neo4j=mock_neo4j, openalex=mock_openalex)
    mat_svc = get_matrix_service(neo4j=mock_neo4j)
    assert ing_svc.neo4j is mock_neo4j and ing_svc.openalex is mock_openalex
    assert svpl_svc._neo4j is mock_neo4j and svpl_svc._openalex is mock_openalex
    assert rem_svc.neo4j is mock_neo4j and rem_svc.openalex is mock_openalex
    assert mat_svc.neo4j is mock_neo4j


# ---------------------------------------------------------------------------
# Section 2: Agent Tool Accessibility & Declarations
# ---------------------------------------------------------------------------

def test_search_snowball_agent_has_exact_tools() -> None:
    """Verify SearchSnowballAgent has exactly 9 tools including all 4 enhancement tools."""
    agent = create_search_snowball_agent()
    names = [getattr(t, "__name__", getattr(t, "name", "")) for t in agent.tools]
    expected = [
        "run_alrs_snowballing_tool", "ingest_user_paper_tool",
        "confirm_title_ingestion_tool", "svpl_multi_hop_discovery_tool",
        "run_autonomous_gap_remediation_tool", "get_project_state",
        "post_to_message_board", "read_message_board", "complete_stage",
    ]
    assert len(agent.tools) == 9
    assert set(names) == set(expected)


def test_methodology_architect_has_exact_tools() -> None:
    """Verify MethodologyArchitect has exactly 6 tools including matrix synthesis tool."""
    agent = create_methodology_architect_agent()
    names = [getattr(t, "__name__", getattr(t, "name", "")) for t in agent.tools]
    expected = [
        "synthesize_comparison_matrix_tool", "generate_section_synthesis_matrix_tool",
        "get_project_state", "post_to_message_board",
        "read_message_board", "complete_stage",
    ]
    assert len(agent.tools) == 6
    assert set(names) == set(expected)


def test_critic_agents_have_no_enhancement_mutation_tools() -> None:
    """Verify auditor/critic agents do NOT have access to state-mutating enhancement tools."""
    auditor = create_relevance_quality_auditor_agent()
    challenger = create_novelty_rigor_challenger_agent()
    forbidden = {
        "ingest_user_paper_tool", "confirm_title_ingestion_tool",
        "svpl_multi_hop_discovery_tool", "run_autonomous_gap_remediation_tool",
        "generate_section_synthesis_matrix_tool",
    }
    auditor_names = {getattr(t, "__name__", getattr(t, "name", "")) for t in auditor.tools}
    challenger_names = {getattr(t, "__name__", getattr(t, "name", "")) for t in challenger.tools}
    assert auditor_names.isdisjoint(forbidden)
    assert challenger_names.isdisjoint(forbidden)


def test_enhancement_tools_are_async_and_have_docstrings() -> None:
    """Verify all 5 enhancement tools are async coroutines with descriptive docstrings."""
    tools = [
        ingest_user_paper_tool, confirm_title_ingestion_tool,
        svpl_multi_hop_discovery_tool, run_autonomous_gap_remediation_tool,
        generate_section_synthesis_matrix_tool,
    ]
    for tool in tools:
        assert inspect.iscoroutinefunction(tool)
        assert tool.__doc__ is not None and len(tool.__doc__.strip()) > 10


# ---------------------------------------------------------------------------
# Section 3: End-to-End Multi-Agent Simulated Execution Flows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_flow_ingest_paper_via_service_argument() -> None:
    """Simulate agent loop invoking ingest_user_paper_tool with explicit service injection."""
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="success", doi="10.1000/182", openalex_id="W1", title="GNN Review",
        citation_links_created=5, can_expand_deeply=True, max_rq_relevance=0.89,
    ))
    res = await ingest_user_paper_tool("10.1000/182", "proj-adv", service=mock_svc)
    assert res["status"] == "success"
    assert res["doi"] == "10.1000/182"
    assert res["citation_links_created"] == 5
    assert res["can_expand_deeply"] is True


@pytest.mark.asyncio
async def test_agent_flow_ingest_paper_via_tool_context_registry() -> None:
    """Simulate agent loop invoking ingest_user_paper_tool via tool_context service registry."""
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="success", doi="10.1000/ctx", openalex_id="W2", title="Context Ingest",
        citation_links_created=2, can_expand_deeply=False, max_rq_relevance=0.71,
    ))
    ctx = _make_tool_context(ingestion_service=mock_svc)
    res = await ingest_user_paper_tool("10.1000/ctx", "proj-adv", tool_context=ctx)
    assert res["status"] == "success"
    assert res["can_expand_deeply"] is False


@pytest.mark.asyncio
async def test_agent_flow_ingest_paper_fuzzy_title_returns_chip() -> None:
    """Simulate agent receiving unconfirmed title returning pending confirmation chip."""
    chip = TitleConfirmationChip(
        chip_id="chip-456", extracted_title="Attention Paper", resolved_openalex_id="W3",
        resolved_doi="10.48550/arxiv.1706.03762", resolved_title="Attention Is All You Need",
        similarity_score=0.94, status="pending",
    )
    mock_svc = MagicMock()
    mock_svc.ingest_paper = AsyncMock(return_value=IngestUserPaperOutput(
        status="pending_confirmation", doi=None, confirmation_chip=chip,
    ))
    res = await ingest_user_paper_tool("Attention Paper", "proj-adv", service=mock_svc)
    assert res["status"] == "pending_confirmation"
    assert res["confirmation_chip"]["similarity_score"] == 0.94


@pytest.mark.asyncio
async def test_agent_flow_confirm_title_ingestion_confirmed_and_dismissed() -> None:
    """Simulate agent executing confirm_title_ingestion_tool for both confirmed and dismissed."""
    mock_svc = MagicMock()
    mock_svc.confirm_title_chip = AsyncMock(side_effect=[
        ConfirmTitleIngestionOutput(
            status="confirmed", doi="10.1000/conf", openalex_id="W10", title="T1", can_expand_deeply=True
        ),
        ConfirmTitleIngestionOutput(
            status="dismissed", doi=None, openalex_id="W20", title="T2", can_expand_deeply=False
        ),
    ])
    res_conf = await confirm_title_ingestion_tool("c1", "p1", confirmed=True, service=mock_svc)
    res_dism = await confirm_title_ingestion_tool("c2", "p1", confirmed=False, service=mock_svc)
    assert res_conf["status"] == "confirmed" and res_conf["doi"] == "10.1000/conf"
    assert res_dism["status"] == "dismissed" and res_dism["doi"] is None


@pytest.mark.asyncio
async def test_agent_flow_svpl_authorized_explicit_directive() -> None:
    """Simulate agent executing authorized SVPL multi-hop discovery via user directive."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=_make_sample_pathway())
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/s", target_doi="10.1000/t",
        trigger_reason="explicit_user_directive", service=mock_svc,
    )
    assert res["status"] == "success"
    assert res["pathway_id"] == "pw-adv-1"
    assert res["discovered_layer"] == 1


@pytest.mark.asyncio
async def test_agent_flow_svpl_authorized_empty_gap_zero_candidates() -> None:
    """Simulate agent executing authorized SVPL discovery for empty gap when candidate_count=0."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=_make_sample_pathway())
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/s", target_doi="10.1000/t",
        trigger_reason="empty_gap_remediation", candidate_count=0, service=mock_svc,
    )
    assert res["status"] == "success"
    assert res["hop_distance"] == 2


@pytest.mark.asyncio
async def test_agent_flow_svpl_unauthorized_routine_crawl_raises() -> None:
    """Verify routine_crawl raises MultiHopUnauthorizedError per strict necessity gating."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/s", target_doi="10.1000/t", trigger_reason="routine_crawl",
        )


@pytest.mark.asyncio
async def test_agent_flow_svpl_unauthorized_gap_with_candidates_raises() -> None:
    """Verify empty_gap_remediation raises MultiHopUnauthorizedError when candidate_count > 0."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/s", target_doi="10.1000/t",
            trigger_reason="empty_gap_remediation", candidate_count=3,
        )


@pytest.mark.asyncio
async def test_agent_flow_svpl_unauthorized_revoked_token_raises() -> None:
    """Verify revoked authorization token raises MultiHopUnauthorizedError."""
    with pytest.raises(MultiHopUnauthorizedError):
        await svpl_multi_hop_discovery_tool(
            source_doi="10.1000/s", target_doi="10.1000/t",
            trigger_reason="explicit_user_directive", authorization_token="revoked",
        )


@pytest.mark.asyncio
async def test_agent_flow_svpl_via_tool_context_registry() -> None:
    """Simulate agent executing svpl tool with service resolved from ToolContext."""
    mock_svc = MagicMock()
    mock_svc.find_bridge_pathway = AsyncMock(return_value=None)
    ctx = _make_tool_context(svpl_service=mock_svc)
    res = await svpl_multi_hop_discovery_tool(
        source_doi="10.1000/iso_a", target_doi="10.1000/iso_b",
        trigger_reason="explicit_user_directive", tool_context=ctx,
    )
    assert res["status"] == "no_path_found"
    assert res["confidence"] == 0.0


@pytest.mark.asyncio
async def test_agent_flow_gap_remediation_targeted_converged() -> None:
    """Simulate agent executing targeted gap remediation reaching convergence."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.CONVERGED, rq_id="rq-adv-1", iterations_executed=2,
        initial_coverage=0.40, final_coverage=0.78, papers_ingested=["10.1000/p1"],
        mode=RemediationMode.TARGETED, is_open_frontier=False,
    ))
    res = await run_autonomous_gap_remediation_tool("rq-adv-1", "proj-adv", mode="targeted", service=mock_svc)
    assert res["status"] == "converged"
    assert res["final_coverage"] == 0.78
    assert res["iterations_executed"] == 2


@pytest.mark.asyncio
async def test_agent_flow_gap_remediation_exploration_suspension_event() -> None:
    """Simulate agent executing exploration gap remediation pausing with RequestInput event."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.MAX_ITERATIONS_PAUSED, rq_id="rq-pause",
        iterations_executed=3, initial_coverage=0.35, final_coverage=0.52, papers_ingested=[],
        mode=RemediationMode.EXPLORATION, is_open_frontier=False,
    ))
    res = await run_autonomous_gap_remediation_tool("rq-pause", "proj-adv", mode="exploration", service=mock_svc)
    assert res["status"] == "paused_awaiting_input"
    assert "suspension_event" in res
    assert "paused awaiting researcher steering" in res["suspension_event"].message


@pytest.mark.asyncio
async def test_agent_flow_gap_remediation_targeted_frontier() -> None:
    """Simulate agent executing targeted remediation marking Open Research Frontier."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.OPEN_RESEARCH_FRONTIER, rq_id="rq-front",
        iterations_executed=3, initial_coverage=0.25, final_coverage=0.25, papers_ingested=[],
        mode=RemediationMode.TARGETED, is_open_frontier=True,
    ))
    res = await run_autonomous_gap_remediation_tool("rq-front", "proj-adv", mode="targeted", service=mock_svc)
    assert res["status"] == "open_research_frontier"
    assert res["is_open_frontier"] is True


@pytest.mark.asyncio
async def test_agent_flow_gap_remediation_via_tool_context() -> None:
    """Simulate agent executing remediation with service resolved from ToolContext."""
    mock_svc = MagicMock()
    mock_svc.run_remediation_loop = AsyncMock(return_value=RunAutonomousGapRemediationOutput(
        status=RemediationCycleStatus.CONVERGED, rq_id="rq-ctx", iterations_executed=1,
        initial_coverage=0.5, final_coverage=0.8, papers_ingested=[], mode=RemediationMode.TARGETED,
    ))
    ctx = _make_tool_context(remediation_service=mock_svc)
    res = await run_autonomous_gap_remediation_tool("rq-ctx", "p1", tool_context=ctx)
    assert res["status"] == "converged"


@pytest.mark.asyncio
async def test_agent_flow_section_matrix_grounded_success() -> None:
    """Simulate MethodologyArchitect generating section matrix with 100% verified DOIs."""
    mock_svc = MagicMock()
    mock_svc.generate_section_matrix = AsyncMock(return_value=GenerateSectionSynthesisMatrixOutput(
        status="success", matrix_id="mat-adv-1", section_id="sec_04",
        dimensions=_make_sample_dimensions(), paper_count=2,
        verified_dois=["10.1000/1", "10.1000/2"],
        markdown_path="stage_04_artifacts/matrices/sec_04.md",
    ))
    res = await generate_section_synthesis_matrix_tool("sec_04", "proj-adv", service=mock_svc)
    assert res["status"] == "success"
    assert res["matrix_id"] == "mat-adv-1"
    assert len(res["dimensions"]) == 3


@pytest.mark.asyncio
async def test_agent_flow_section_matrix_ungrounded_raises_citation_hallucination() -> None:
    """Verify ungrounded DOI strictly raises CitationHallucinationError per Constitution A37."""
    mock_svc = MagicMock()
    mock_svc.generate_section_matrix = AsyncMock(
        side_effect=CitationHallucinationError("10.9999/phantom", "sec_04")
    )
    with pytest.raises(CitationHallucinationError):
        await generate_section_synthesis_matrix_tool("sec_04", "proj-adv", service=mock_svc)


@pytest.mark.asyncio
async def test_agent_flow_section_matrix_via_tool_context() -> None:
    """Simulate MethodologyArchitect executing matrix tool via ToolContext registry."""
    mock_svc = MagicMock()
    mock_svc.generate_section_matrix = AsyncMock(return_value=GenerateSectionSynthesisMatrixOutput(
        status="success", matrix_id="mat-ctx", section_id="sec_05",
        dimensions=_make_sample_dimensions(), paper_count=1,
        verified_dois=["10.1000/p1"], markdown_path="stage_04_artifacts/matrices/sec_05.md",
    ))
    ctx = _make_tool_context(matrix_service=mock_svc)
    res = await generate_section_synthesis_matrix_tool("sec_05", "proj-adv", tool_context=ctx)
    assert res["status"] == "success"


# ---------------------------------------------------------------------------
# Section 4: PaperRead Serialization & API Contract Invariants
# ---------------------------------------------------------------------------

def test_paper_read_fastapi_response_model_serialization() -> None:
    """Verify FastAPI endpoint returning PaperRead serializes correctly via HTTP."""
    app = FastAPI()

    @app.get("/paper", response_model=PaperRead)
    def route_paper() -> PaperRead:
        return PaperRead(doi="10.1000/adv", title="FastAPI Paper", is_stub=True, is_bridge=True)

    client = TestClient(app)
    resp = client.get("/paper")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doi"] == "10.1000/adv"
    assert data["is_stub"] is True
    assert data["is_bridge"] is True
    assert "embedding" not in data


def test_paper_read_legacy_payload_defaults() -> None:
    """Verify legacy API payloads seamlessly parse with expected enhancement flag defaults."""
    legacy_payload: dict[str, Any] = {
        "doi": "10.1145/1234567.890", "title": "Legacy Paper Title",
        "abstract": "Legacy abstract text.", "year": 2020, "cited_by_count": 42,
    }
    paper = PaperRead.model_validate(legacy_payload)
    assert paper.doi == "10.1145/1234567.890"
    assert paper.is_stub is False
    assert paper.is_bridge is False
    assert paper.can_expand_deeply is True
    assert paper.is_retracted is False


def test_paper_read_extra_fields_resilience() -> None:
    """Verify PaperRead ignores unknown extra fields from external sources without error."""
    payload = {
        "doi": "10.1000/extra", "title": "Extra Fields Test",
        "unknown_future_field": "some_value", "another_extra": 12345,
    }
    paper = PaperRead.model_validate(payload)
    assert paper.doi == "10.1000/extra"
    assert not hasattr(paper, "unknown_future_field")


def test_paper_read_zero_ram_policy_strictness() -> None:
    """Verify PaperRead strictly prohibits embedding and embeddings fields (Constitution A5)."""
    assert "embedding" not in PaperRead.model_fields
    assert "embeddings" not in PaperRead.model_fields
    paper = PaperRead(doi="10.1000/no_ram", title="Zero RAM Paper")
    assert not hasattr(paper, "embedding")
    assert not hasattr(paper, "embeddings")
    serialized = paper.model_dump(mode="json")
    assert "embedding" not in serialized


def test_paper_read_full_roundtrip_with_predicates() -> None:
    """Verify JSON roundtrip retains all boolean predicates and field types accurately."""
    original = PaperRead(
        doi="10.1000/roundtrip_adv", title="Roundtrip Paper",
        is_stub=True, is_bridge=True, can_expand_deeply=False, is_retracted=True,
    )
    raw_json = original.model_dump_json()
    restored = PaperRead.model_validate_json(raw_json)
    assert restored == original
    assert restored.can_expand_deeply is False
    assert restored.is_retracted is True


def test_paper_read_boolean_type_coercion() -> None:
    """Verify boolean predicate fields coerce truthy and falsy values as expected."""
    paper = PaperRead(
        doi="10.1000/coercion", title="Coercion Paper",
        is_stub=1, is_bridge=0, can_expand_deeply=1, is_retracted=0,  # type: ignore[arg-type]
    )
    assert paper.is_stub is True
    assert paper.is_bridge is False
    assert paper.can_expand_deeply is True
    assert paper.is_retracted is False
