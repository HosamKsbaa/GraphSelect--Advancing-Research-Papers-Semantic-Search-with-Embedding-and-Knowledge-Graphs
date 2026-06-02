"""Export API endpoints for ALRS v2.

Thin FastAPI router that delegates to :class:`ExportService` for
BibTeX, LaTeX, and citation graph export operations.

Endpoints:
    POST  /api/export/{project_id}/bibtex          → export_bibtex
    POST  /api/export/{project_id}/latex            → export_latex
    POST  /api/export/{project_id}/citation-graph   → export_citation_graph
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


# ── Request models ───────────────────────────────────────────────────

class LatexRequest(BaseModel):
    """Body for the LaTeX export endpoint."""

    template: str = Field(default="ieee", description="LaTeX template: 'ieee', 'acm', or 'plain'")


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/{project_id}/bibtex")
async def export_bibtex(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Export the project's paper library as a BibTeX file."""
    from features.export.service import ExportService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    mysql = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None

    settings = get_settings()
    service = ExportService(
        neo4j=neo4j,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    return await service.export_bibtex(project_id)


@router.post("/{project_id}/latex")
async def export_latex(
    project_id: str,
    body: LatexRequest,
    request: Request,
) -> dict[str, Any]:
    """Convert approved Markdown draft sections into a LaTeX document."""
    from features.export.service import ExportService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    mysql = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None

    settings = get_settings()
    service = ExportService(
        neo4j=neo4j,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    result = await service.export_latex(project_id, template=body.template)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["error"],
        )

    return result


@router.post("/{project_id}/citation-graph")
async def export_citation_graph(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Export the project's citation network as JSON + GraphML."""
    from features.export.service import ExportService
    from config import get_settings
    from core.logging.log_service import LogService

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    mysql = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None

    settings = get_settings()
    service = ExportService(
        neo4j=neo4j,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )
    result = await service.export_citation_graph(project_id)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    return result
