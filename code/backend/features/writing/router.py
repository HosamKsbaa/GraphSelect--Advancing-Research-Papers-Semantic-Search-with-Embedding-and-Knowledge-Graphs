"""Writing API endpoints for ALRS v2.

Thin FastAPI router that delegates to :class:`WritingService` for
paper abstract retrieval, section drafting, citation verification, and section review.

Endpoints:
    POST  /api/writing/{project_id}/abstracts         → get_paper_abstracts
    POST  /api/writing/{project_id}/draft             → draft_section
    POST  /api/writing/{project_id}/review            → review_section
    POST  /api/writing/{project_id}/verify-citations  → verify_citations
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from features.writing.models import (
    AbstractsRequest,
    DraftRequest,
    ReviewRequest,
    CitationVerificationRequest,
    CitationVerificationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/writing", tags=["writing"])


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/{project_id}/abstracts")
async def get_paper_abstracts(
    project_id: str,
    body: AbstractsRequest,
    request: Request,
) -> dict[str, Any]:
    """Retrieve abstracts for a list of papers to provide writing context."""
    from features.writing.service import WritingService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    settings = get_settings()
    service = WritingService(
        neo4j=neo4j,
        llm=None,  # type: ignore[arg-type]  # not needed for abstracts
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    return await service.get_paper_abstracts(project_id, body.dois)


@router.post("/{project_id}/draft")
async def draft_section(
    project_id: str,
    body: DraftRequest,
    request: Request,
) -> dict[str, Any]:
    """Draft a single section of the literature review using the LLM."""
    from features.writing.service import WritingService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    llm = getattr(request.app.state, "llm_service", None)
    if neo4j is None or llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required services not initialized",
        )

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    settings = get_settings()
    service = WritingService(
        neo4j=neo4j,
        llm=llm,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    return await service.draft_section(
        project_id=project_id,
        section_title=body.section_title,
        section_description=body.section_description,
        paper_dois=body.paper_dois,
        target_level=body.target_level,
        outline_context=body.outline_context,
    )


@router.post("/{project_id}/review")
async def review_section(
    project_id: str,
    body: ReviewRequest,
    request: Request,
) -> dict[str, Any]:
    """Review a drafted section for accuracy, completeness, and coherence."""
    from features.writing.service import WritingService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    llm = getattr(request.app.state, "llm_service", None)
    if neo4j is None or llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required services not initialized",
        )

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    settings = get_settings()
    service = WritingService(
        neo4j=neo4j,
        llm=llm,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    return await service.review_section(
        project_id=project_id,
        section_title=body.section_title,
        draft_text=body.draft_text,
        paper_dois=body.paper_dois,
        target_level=body.target_level,
    )


@router.post("/{project_id}/verify-citations", response_model=CitationVerificationResponse)
async def verify_citations(
    project_id: str,
    body: CitationVerificationRequest,
    request: Request,
) -> dict[str, Any]:
    """Verify in-text citations against the Neo4j knowledge graph and assigned paper DOIs."""
    from features.writing.service import WritingService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    settings = get_settings()
    service = WritingService(
        neo4j=neo4j,
        llm=getattr(request.app.state, "llm_service", None),
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    try:
        return await service.verify_citations(
            project_id=project_id,
            draft_text=body.draft_text,
            assigned_dois=body.assigned_dois,
        )
    except Exception as exc:
        logger.exception("verify_citations endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

