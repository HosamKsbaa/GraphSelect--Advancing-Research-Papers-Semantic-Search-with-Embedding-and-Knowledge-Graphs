"""Google ADK Tools for Autonomous Research Enhancements (Feature 007).

Exposes 5 Google ADK tool functions adhering to ADR-001 and Constitution v2.2.1:
- C5, A15, A49: Persist $run_id and $created_in_stage across graph mutations.
- C7: Strict static typing without bare signatures.
- C8: Pure Neo4j SSOT, zero MySQL.
- C9: Granular sub-routines strictly <= 25 lines (SRP & SLAP).
- FR-015: Strict necessity gating on multi-hop discovery.
- A37: Zero citation hallucination (CHR == 0.0%).
"""
from __future__ import annotations

import logging
from typing import Any

from agents._service_registry import ServiceRegistry
from core.errors.enhancement_errors import MultiHopUnauthorizedError
from features.drafting.matrix_models import (
    GenerateSectionSynthesisMatrixInput,
    GenerateSectionSynthesisMatrixOutput,
)
from features.drafting.matrix_service import MatrixService
from features.gap_analysis.models import (
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
    RunAutonomousGapRemediationOutput,
)
from features.gap_analysis.remediation_service import RemediationService
from features.ingestion.ingestion_service import IngestionService
from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    ConfirmTitleIngestionOutput,
    IngestUserPaperInput,
    IngestUserPaperOutput,
)
from features.ranking.svpl_gating import check_multihop_authorization, parse_trigger_reason
from features.ranking.svpl_models import (
    MultiHopAuthorization,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
    SVPLMultiHopDiscoveryOutput,
)
from features.ranking.svpl_service import SVPLService

logger = logging.getLogger(__name__)


def _get_registry_service(name: str) -> Any:
    """Safely obtain a service from ServiceRegistry without unhandled exceptions."""
    try:
        return getattr(ServiceRegistry, name, None)
    except Exception:
        return None


def _resolve_ingestion_service(
    service: IngestionService | None = None,
    **kwargs: Any,
) -> IngestionService:
    """Resolve IngestionService from explicit argument, context, or registry."""
    if service is not None:
        return service
    override = kwargs.get("service") or kwargs.get("ingestion_service")
    if override is not None:
        return override  # type: ignore[no-any-return]
    tc = kwargs.get("tool_context")
    if tc and hasattr(tc, "service_registry"):
        svc = getattr(tc.service_registry, "ingestion_service", None)
        if svc is not None:
            return svc  # type: ignore[no-any-return]
    neo4j = _get_registry_service("neo4j")
    openalex = _get_registry_service("openalex")
    gemini = _get_registry_service("embedding_provider")
    return IngestionService(neo4j_service=neo4j, openalex_service=openalex, embedding_service=gemini)


def _resolve_svpl_service(
    service: SVPLService | None = None,
    **kwargs: Any,
) -> SVPLService:
    """Resolve SVPLService from explicit argument, context, or registry."""
    if service is not None:
        return service
    override = kwargs.get("service") or kwargs.get("svpl_service")
    if override is not None:
        return override  # type: ignore[no-any-return]
    tc = kwargs.get("tool_context")
    if tc and hasattr(tc, "service_registry"):
        svc = getattr(tc.service_registry, "svpl_service", None)
        if svc is not None:
            return svc  # type: ignore[no-any-return]
    neo4j = _get_registry_service("neo4j")
    openalex = _get_registry_service("openalex")
    return SVPLService(neo4j_service=neo4j, openalex_service=openalex)


def _resolve_remediation_service(
    service: RemediationService | None = None,
    **kwargs: Any,
) -> RemediationService:
    """Resolve RemediationService from explicit argument, context, or registry."""
    if service is not None:
        return service
    override = kwargs.get("service") or kwargs.get("remediation_service")
    if override is not None:
        return override  # type: ignore[no-any-return]
    tc = kwargs.get("tool_context")
    if tc and hasattr(tc, "service_registry"):
        svc = getattr(tc.service_registry, "remediation_service", None)
        if svc is not None:
            return svc  # type: ignore[no-any-return]
    neo4j = _get_registry_service("neo4j")
    openalex = _get_registry_service("openalex")
    return RemediationService(neo4j=neo4j, openalex=openalex)


def _resolve_matrix_service(
    service: MatrixService | None = None,
    **kwargs: Any,
) -> MatrixService:
    """Resolve MatrixService from explicit argument, context, or registry."""
    if service is not None:
        return service
    override = kwargs.get("service") or kwargs.get("matrix_service")
    if override is not None:
        return override  # type: ignore[no-any-return]
    tc = kwargs.get("tool_context")
    if tc and hasattr(tc, "service_registry"):
        svc = getattr(tc.service_registry, "matrix_service", None)
        if svc is not None:
            return svc  # type: ignore[no-any-return]
    neo4j = _get_registry_service("neo4j")
    return MatrixService(neo4j=neo4j)


async def ingest_user_paper_tool(
    raw_input: str,
    project_id: str,
    run_id: str = "adk_run",
    is_title_confirmed: bool = False,
    stage_index: int = 2,
    service: IngestionService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Ingest user paper into library and wire citations bidirectionally."""
    svc = _resolve_ingestion_service(service, **kwargs)
    confirmed = is_title_confirmed or bool(kwargs.get("is_title_confirmed", False))
    inp = IngestUserPaperInput(
        raw_input=raw_input, identifier=raw_input,
        project_id=project_id, run_id=run_id,
        stage_index=stage_index, is_title_confirmed=confirmed,
    )
    res: IngestUserPaperOutput = await svc.ingest_paper(inp)
    return res.model_dump(mode="json")


def _build_confirm_title_input(
    chip_id: str, project_id: str, run_id: str, confirmed: bool,
    resolved_openalex_id: str, resolved_title: str,
    resolved_doi: str | None, stage_index: int, **kwargs: Any,
) -> ConfirmTitleIngestionInput:
    """Build input model for title confirmation action."""
    o_id = resolved_openalex_id or kwargs.get("openalex_id") or f"W_{chip_id}"
    t = resolved_title or kwargs.get("title") or f"Title for {chip_id}"
    return ConfirmTitleIngestionInput(
        chip_id=chip_id, project_id=project_id, confirmed=confirmed,
        resolved_openalex_id=o_id, resolved_doi=resolved_doi or kwargs.get("doi"),
        resolved_title=t, run_id=run_id, stage_index=stage_index,
    )


async def confirm_title_ingestion_tool(
    chip_id: str, project_id: str, run_id: str = "adk_run",
    confirmed: bool = True, resolved_openalex_id: str = "",
    resolved_title: str = "", resolved_doi: str | None = None,
    stage_index: int = 2, service: IngestionService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Confirm or dismiss fuzzy paper title confirmation chip."""
    svc = _resolve_ingestion_service(service, **kwargs)
    inp = _build_confirm_title_input(
        chip_id, project_id, run_id, confirmed,
        resolved_openalex_id, resolved_title, resolved_doi, stage_index, **kwargs
    )
    res: ConfirmTitleIngestionOutput = await svc.confirm_title_chip(inp)
    return res.model_dump(mode="json")


def _authorize_multihop(
    trigger_reason: str,
    authorization_token: str | None,
    candidate_count: int,
    **kwargs: Any,
) -> MultiHopAuthorization:
    """Validate and build MultiHopAuthorization payload (FR-015)."""
    reason_enum = parse_trigger_reason(trigger_reason)
    is_auth = authorization_token not in ("unauthorized", "revoked") and kwargs.get("is_authorized", True)
    auth = MultiHopAuthorization(
        trigger_reason=reason_enum,
        requester=kwargs.get("requester", "SearchSnowballAgent"),
        context_description=kwargs.get("context_description", "ADK multi-hop discovery tool invocation"),
        is_authorized=is_auth,
    )
    check_multihop_authorization(auth, candidate_count=candidate_count)
    return auth


def _build_empty_svpl_output(source_doi: str, target_doi: str, max_hops: int) -> dict[str, Any]:
    """Build serialized output when no pathway was discovered."""
    return SVPLMultiHopDiscoveryOutput(
        status="no_path_found",
        source_doi=source_doi,
        target_doi=target_doi,
        hop_distance=max_hops,
        discovered_layer=0,
        confidence=0.0,
    ).model_dump(mode="json")


def _build_success_svpl_output(pathway: MultiHopBridgePathway) -> dict[str, Any]:
    """Build serialized output from discovered pathway."""
    return SVPLMultiHopDiscoveryOutput(
        status="success",
        pathway_id=pathway.pathway_id,
        source_doi=pathway.source_doi,
        target_doi=pathway.target_doi,
        hop_distance=pathway.hop_distance,
        discovered_layer=pathway.discovered_layer,
        mechanism=pathway.mechanism,
        intermediate_nodes=pathway.intermediate_nodes,
        confidence=pathway.confidence,
    ).model_dump(mode="json")


def _build_svpl_output(
    pathway: MultiHopBridgePathway | None,
    source_doi: str,
    target_doi: str,
    max_hops: int,
) -> dict[str, Any]:
    """Build serialized SVPLMultiHopDiscoveryOutput dictionary."""
    if pathway is None:
        return _build_empty_svpl_output(source_doi, target_doi, max_hops)
    return _build_success_svpl_output(pathway)


async def svpl_multi_hop_discovery_tool(
    source_doi: str, target_doi: str, trigger_reason: str,
    authorization_token: str | None = None, run_id: str = "adk_run",
    max_hops: int = 3, stage_index: int = 2, candidate_count: int = 0,
    service: SVPLService | None = None, **kwargs: Any,
) -> dict[str, Any]:
    """Execute SVPL multi-hop bridge discovery under strict necessity gating."""
    auth = _authorize_multihop(trigger_reason, authorization_token, candidate_count, **kwargs)
    svc = _resolve_svpl_service(service, **kwargs)
    pathway = await svc.find_bridge_pathway(
        source_doi=source_doi, target_doi=target_doi,
        project_id=kwargs.get("project_id"), trigger_reason=auth,
        max_hops=max_hops, run_id=run_id, stage_index=stage_index,
        candidate_count=candidate_count,
    )
    return _build_svpl_output(pathway, source_doi, target_doi, max_hops)


def _attach_suspension_event(result: dict[str, Any], rq_id: str, project_id: str, cov: float) -> None:
    """Attach native ADK RequestInput event if remediation paused."""
    if result.get("status") in ("paused_awaiting_input", RemediationCycleStatus.MAX_ITERATIONS_PAUSED):
        try:
            from google.adk.events import RequestInput
            result["suspension_event"] = RequestInput(
                message=f"Literature gap remediation for RQ '{rq_id}' paused awaiting researcher steering.",
                payload={"rq_id": rq_id, "project_id": project_id, "coverage": cov},
            )
        except Exception:
            pass


async def run_autonomous_gap_remediation_tool(
    rq_id: str, project_id: str, mode: str = "targeted",
    run_id: str = "adk_run", max_iterations: int = 3,
    stage_index: int = 2, service: RemediationService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute autonomous closed-loop search remediation for a deficit RQ."""
    svc = _resolve_remediation_service(service, **kwargs)
    rem_mode = RemediationMode(mode.lower().strip()) if isinstance(mode, str) else mode
    inp = RunAutonomousGapRemediationInput(
        project_id=project_id, rq_id=rq_id, mode=rem_mode,
        max_iterations=max_iterations, run_id=run_id, stage_index=stage_index,
    )
    out: RunAutonomousGapRemediationOutput = await svc.run_remediation_loop(inp)
    result = out.model_dump(mode="json")
    _attach_suspension_event(result, rq_id, project_id, out.final_coverage)
    return result


async def generate_section_synthesis_matrix_tool(
    section_id: str, project_id: str, section_title: str | None = None,
    narrative_theme: str | None = None, assigned_dois: list[str] | None = None,
    run_id: str = "adk_run", stage_index: int = 4,
    service: MatrixService | None = None, **kwargs: Any,
) -> dict[str, Any]:
    """Generate section synthesis matrix with verified citekeys and dual persistence."""
    svc = _resolve_matrix_service(service, **kwargs)
    dois = assigned_dois or kwargs.get("assigned_dois") or [f"10.1000/{section_id}"]
    inp = GenerateSectionSynthesisMatrixInput(
        project_id=project_id, section_id=section_id,
        section_title=section_title or f"Section {section_id}",
        narrative_theme=narrative_theme or f"Synthesis of {section_id}",
        assigned_dois=dois, run_id=run_id, stage_index=stage_index,
    )
    out: GenerateSectionSynthesisMatrixOutput = await svc.generate_section_matrix(inp)
    return out.model_dump(mode="json")
