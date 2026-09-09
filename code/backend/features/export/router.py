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

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


# ── Request models ───────────────────────────────────────────────────

class LatexRequest(BaseModel):
    """Body for the LaTeX export endpoint."""

    template: str = Field(default="ieee", description="LaTeX template: 'ieee', 'acm', or 'plain'")


class PdfExportRequest(BaseModel):
    """Body for the PDF export endpoint."""

    template: str = Field(default="plain", description="LaTeX template: 'plain', 'ieee', or 'acm'")
    download: bool = Field(default=False, description="Whether to return downloadable binary FileResponse")
    timeout_sec: int = Field(default=30, description="Compilation timeout in seconds")


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

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

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

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

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

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

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


@router.post("/{project_id}/pdf", response_model=None)
async def export_pdf(
    project_id: str,
    request: Request,
    body: PdfExportRequest | None = None,
) -> Response | dict[str, Any]:
    """Compile project drafts to a PDF document and return download response or path metadata."""
    from features.export.service import ExportService
    from config import get_settings
    from core.logging.log_service import LogService

    if body is None:
        body = PdfExportRequest()

    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    settings = get_settings()
    service = ExportService(
        neo4j=neo4j,
        log_service=log_service,
        projects_dir=settings.projects_dir,
    )

    try:
        pdf_path = await service.compile_pdf(
            project_id=project_id,
            template=body.template,
            timeout_sec=body.timeout_sec,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF compilation failed: {exc}",
        )

    if body.download:
        return FileResponse(
            path=str(pdf_path),
            filename=f"literature_review_{body.template}.pdf",
            media_type="application/pdf",
        )

    return {
        "status": "success",
        "pdf_path": str(pdf_path),
        "template": body.template,
        "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "filename": pdf_path.name,
    }

