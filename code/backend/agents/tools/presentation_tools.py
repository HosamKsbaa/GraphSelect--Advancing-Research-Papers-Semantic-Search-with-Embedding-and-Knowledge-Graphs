"""Google ADK typed tools for Presentation Generation and Grounding Verification.

Conforms to ADR-001 and Constitution Rules A28, A33, A36, C7, C9.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from features.export.fact_auditor import PresentationFactAuditor
from features.export.presentation_models import (
    AuditSlideGroundingRequest,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorDetail,
    PresentationErrorCode,
    SlideGroundingCriticReport,
)
from features.export.presentation_service import PresentationService

logger = logging.getLogger(__name__)


def _resolve_presentation_service(tool_context: ToolContext | None) -> PresentationService:
    """Resolve PresentationService instance from ToolContext or singleton ServiceRegistry."""
    if tool_context and hasattr(tool_context, "service_registry"):
        svc = getattr(tool_context.service_registry, "presentation_service", None)
        if svc:
            return svc
    if hasattr(ServiceRegistry, "presentation_service"):
        return ServiceRegistry.presentation_service
    neo4j = getattr(ServiceRegistry, "neo4j", None)
    return PresentationService(neo4j=neo4j)


async def generate_presentation_deck_tool(
    request: PresentationDeckRequest,
    tool_context: ToolContext | None = None,
) -> PresentationDeckResponse:
    """Extract graph facts, synthesize slides, verify grounding, and compile standalone deck."""
    service = _resolve_presentation_service(tool_context)
    try:
        return await service.generate_deck(request)
    except ValueError as exc:
        err_msg = str(exc)
        code = (
            PresentationErrorCode.INVALID_SLIDE_RANGE
            if PresentationErrorCode.INVALID_SLIDE_RANGE.value in err_msg
            else (
                PresentationErrorCode.PROJECT_NOT_FOUND
                if PresentationErrorCode.PROJECT_NOT_FOUND.value in err_msg
                else PresentationErrorCode.EMPTY_LIBRARY_WARNING
            )
        )
        return _build_tool_error_response(code, err_msg)
    except Exception as exc:
        logger.exception("Unexpected failure during presentation generation: %s", exc)
        return _build_tool_error_response(PresentationErrorCode.PERSISTENCE_ERROR, str(exc))


def _build_tool_error_response(code: PresentationErrorCode, message: str) -> PresentationDeckResponse:
    """Construct deterministic structured error response conforming to ADR-001."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return PresentationDeckResponse(
        success=False,
        file_path="",
        slide_count=0,
        generated_timestamp=now_iso,
        facts_verified_count=0,
        preview_html="",
        sha256_hash="",
        error=PresentationErrorDetail(
            code=code,
            message=message,
            details={},
            recovery_guidance="Verify campaign state and inputs in Neo4j SSOT.",
        ),
    )


async def audit_slide_grounding_tool(
    request: AuditSlideGroundingRequest,
    tool_context: ToolContext | None = None,
) -> SlideGroundingCriticReport:
    """Audit slide citations, metric precision, and zero-hallucination compliance against Neo4j."""
    neo4j = getattr(ServiceRegistry, "neo4j", None)
    if tool_context and hasattr(tool_context, "service_registry"):
        neo4j = getattr(tool_context.service_registry, "neo4j", neo4j)
    if not neo4j:
        return _build_uninitialized_audit_report("Neo4j SSOT service unavailable for audit")
    try:
        auditor = PresentationFactAuditor(neo4j)
        return await auditor.audit_slides(request.project_id, request.slides)
    except Exception as exc:
        logger.exception("Slide grounding audit failed: %s", exc)
        return _build_uninitialized_audit_report(f"Grounding audit query error: {exc}")


def _build_uninitialized_audit_report(reason: str) -> SlideGroundingCriticReport:
    """Construct deterministic rejection report when audit cannot connect to Neo4j."""
    return SlideGroundingCriticReport(
        is_grounded=False,
        measured_chr=100.0,
        composite_score=0.0,
        dimension_scores={
            "citation_grounding": 0.0,
            "metric_fidelity": 0.0,
            "structural_integrity": 0.0,
            "notes_completeness": 0.0,
        },
        violations=[reason],
        actionable_directives=["Ensure Neo4j graph service is connected and operational"],
    )
