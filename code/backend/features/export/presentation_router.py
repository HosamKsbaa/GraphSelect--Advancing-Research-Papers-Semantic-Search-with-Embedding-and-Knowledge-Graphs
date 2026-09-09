"""FastAPI router for Presentation Deck generation, inspection, and export.

Conforms to contracts/presentation_api.yaml and Constitution v2.2.1 (C7, C8, C9 <=25 line handlers).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse

from config import get_settings
from features.export.presentation_models import (
    PresentationDeckArtifact,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorDetail,
    PresentationErrorCode,
)
from features.export.presentation_service import PresentationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["presentation"])


def _get_presentation_service(request: Request) -> PresentationService:
    """Resolve PresentationService instance from FastAPI application state."""
    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized in application state",
        )
    settings = get_settings()
    log_service = getattr(request.app.state, "log_service", None)
    return PresentationService(
        neo4j=neo4j,
        projects_dir=settings.projects_dir,
        log_service=log_service,
    )


async def _broadcast_sse_event(request: Request, project_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Safely publish presentation event to SSE progress stream if initialized."""
    progress = getattr(request.app.state, "progress_service", None)
    if not progress:
        return
    try:
        if hasattr(progress, "emit"):
            from core.logging.progress_service import ProgressEvent
            evt = ProgressEvent(phase="export", status=event_type, message=f"Presentation {event_type}", details=data)
            await progress.emit(project_id, evt)
        elif hasattr(progress, "publish"):
            res = progress.publish(project_id, {"type": event_type, **data})
            if hasattr(res, "__await__"):
                await res
    except Exception:
        pass


@router.post(
    "/{project_id}/presentation",
    response_model=PresentationDeckResponse,
    responses={
        400: {"model": PresentationErrorDetail},
        404: {"model": PresentationErrorDetail},
        422: {"model": PresentationErrorDetail},
        500: {"model": PresentationErrorDetail},
    },
)
async def generate_presentation_deck(
    project_id: str,
    body: PresentationDeckRequest,
    request: Request,
) -> PresentationDeckResponse:
    """Generate an interactive standalone HTML presentation deck."""
    service = _get_presentation_service(request)
    if body.project_id != project_id:
        body = body.model_copy(update={"project_id": project_id})

    await _broadcast_sse_event(request, project_id, "presentation_started", {"stage": "init"})
    try:
        resp = await service.generate_deck(body)
    except ValueError as exc:
        return _handle_service_value_error(str(exc))
    except Exception as exc:
        return _handle_service_unexpected_error(str(exc))

    if not resp.success and resp.error:
        _handle_response_error(resp.error)

    await _broadcast_sse_event(request, project_id, "presentation_completed", {"file_path": resp.file_path})
    return resp


def _handle_service_value_error(msg: str) -> Any:
    """Map service ValueError to appropriate HTTP error status code."""
    if PresentationErrorCode.INVALID_SLIDE_RANGE.value in msg:
        code = PresentationErrorCode.INVALID_SLIDE_RANGE
        st = status.HTTP_400_BAD_REQUEST
    elif PresentationErrorCode.PROJECT_NOT_FOUND.value in msg:
        code = PresentationErrorCode.PROJECT_NOT_FOUND
        st = status.HTTP_404_NOT_FOUND
    else:
        code = PresentationErrorCode.EMPTY_LIBRARY_WARNING
        st = status.HTTP_422_UNPROCESSABLE_ENTITY
    err = PresentationErrorDetail(code=code, message=msg, details={}, recovery_guidance="Review input parameters.")
    raise HTTPException(status_code=st, detail=err.model_dump())


def _handle_service_unexpected_error(msg: str) -> Any:
    """Map unexpected exceptions to HTTP 500 error."""
    err = PresentationErrorDetail(
        code=PresentationErrorCode.PERSISTENCE_ERROR,
        message=msg,
        details={},
        recovery_guidance="Check server disk permissions and database connectivity.",
    )
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err.model_dump())


def _handle_response_error(error: PresentationErrorDetail) -> None:
    """Map structured response error to HTTP exception code."""
    st_map = {
        PresentationErrorCode.PROJECT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        PresentationErrorCode.INVALID_SLIDE_RANGE: status.HTTP_400_BAD_REQUEST,
        PresentationErrorCode.GROUNDING_VERIFICATION_FAILED: status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    st = st_map.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=st, detail=error.model_dump())


@router.get("/{project_id}/presentation/latest", response_model=PresentationDeckArtifact)
async def get_latest_presentation(project_id: str, request: Request) -> PresentationDeckArtifact:
    """Retrieve metadata for the latest generated presentation deck."""
    service = _get_presentation_service(request)
    deck = await service.get_latest_deck(project_id)
    if not deck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No presentations for project {project_id}")
    return deck


@router.get("/{project_id}/presentations", response_model=list[PresentationDeckArtifact])
async def list_presentations(project_id: str, request: Request) -> list[PresentationDeckArtifact]:
    """List all generated presentation decks for a project."""
    service = _get_presentation_service(request)
    return await service.list_decks(project_id)


@router.get("/{project_id}/presentation/{artifact_id}/download")
async def download_presentation_html(project_id: str, artifact_id: str, request: Request) -> FileResponse:
    """Download the standalone self-contained HTML presentation file."""
    service = _get_presentation_service(request)
    deck = await service.get_deck_by_id(project_id, artifact_id)
    if not deck or not Path(deck.file_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation HTML file not found on disk")
    return FileResponse(path=deck.file_path, media_type="text/html", filename=deck.filename)


@router.get("/{project_id}/presentation/{artifact_id}/pdf")
async def download_presentation_pdf(project_id: str, artifact_id: str, request: Request) -> FileResponse:
    """Compile and download 16:9 landscape PDF of presentation slides."""
    service = _get_presentation_service(request)
    deck = await service.get_deck_by_id(project_id, artifact_id)
    if not deck or not Path(deck.file_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation source HTML file not found")
    pdf_path = Path(deck.file_path).with_suffix(".pdf")
    try:
        await service.export_deck_to_pdf(deck.file_path, str(pdf_path))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"PDF compilation failed: {exc}")
    return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=f"{deck.artifact_id}.pdf")
