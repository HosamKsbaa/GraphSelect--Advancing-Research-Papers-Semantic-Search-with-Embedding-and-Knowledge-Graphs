"""Planning API endpoints for ALRS v2.

Thin FastAPI router that delegates to :class:`PlanningService` for
project summary and outline generation.

Endpoints:
    GET   /api/planning/{project_id}/summary   → get_project_summary
    POST  /api/planning/{project_id}/outline    → generate_outline
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planning", tags=["planning"])


# ── Request models ───────────────────────────────────────────────────

class OutlineRequest(BaseModel):
    """Body for the outline generation endpoint."""

    style: str = Field(default="thematic", description="Outline style: thematic, chronological, or methodological")
    num_sections: int | None = Field(default=None, ge=2, le=10, description="Optional number of sections")


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Get a summary of the project's current state for planning.

    Returns paper_count, question_count, gap_count, has_outline,
    has_drafts, and a list of research question texts.
    """
    from features.planning.service import PlanningService
    from config import get_settings

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    settings = get_settings()
    llm = getattr(request.app.state, "llm_service", None)

    service = PlanningService(
        neo4j=neo4j,
        llm=llm,  # type: ignore[arg-type]
        projects_dir=settings.projects_dir,
    )
    return await service.get_project_summary(project_id)


@router.post("/{project_id}/outline")
async def generate_outline(
    project_id: str,
    body: OutlineRequest,
    request: Request,
) -> dict[str, Any]:
    """Generate a structured literature review outline.

    Uses the LLM to create thematic or chronological sections, each with
    assigned papers and descriptive summaries.
    """
    from features.planning.service import PlanningService
    from config import get_settings

    neo4j = getattr(request.app.state, "neo4j_service", None)
    llm = getattr(request.app.state, "llm_service", None)
    if neo4j is None or llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required services not initialized",
        )

    settings = get_settings()
    service = PlanningService(
        neo4j=neo4j,
        llm=llm,
        projects_dir=settings.projects_dir,
    )
    result = await service.generate_outline(
        project_id=project_id,
        style=body.style,
        num_sections=body.num_sections,
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["error"],
        )

    return result
