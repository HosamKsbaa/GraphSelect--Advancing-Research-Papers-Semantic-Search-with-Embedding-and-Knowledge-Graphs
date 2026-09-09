"""FastAPI router exposing continuous literature ingestion endpoints.

Complies with Constitution v2.2.1:
- C7: Strict static typing with Pydantic v2.
- C9: Granular functions under 25 lines (SRP / SLAP).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from core.errors.enhancement_errors import EnhancementToolError, get_http_status_code
from features.ingestion.ingestion_service import IngestionService
from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    ConfirmTitleIngestionOutput,
    IngestUserPaperInput,
    IngestUserPaperOutput,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


def get_ingestion_service(request: Request) -> IngestionService:
    """Dependency provider injecting IngestionService singleton/instance."""
    app_state = request.app.state
    neo4j = getattr(app_state, "neo4j_service", None)
    openalex = getattr(app_state, "openalex_service", None)
    if openalex is None:
        from core.clients.openalex_client import OpenAlexService
        from config import get_settings
        settings = get_settings()
        openalex = OpenAlexService(api_key=settings.openalex_api_key)
        app_state.openalex_service = openalex
    llm = getattr(app_state, "llm_service", None)
    log_svc = getattr(app_state, "log_service", None)
    return IngestionService(
        neo4j_service=neo4j,
        openalex_service=openalex,
        embedding_service=llm,
        log_service=log_svc,
    )


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]


@router.post("/ingest-paper", response_model=IngestUserPaperOutput)
async def ingest_paper_endpoint(
    input_data: IngestUserPaperInput,
    service: IngestionServiceDep,
) -> IngestUserPaperOutput:
    """Ingest a paper referenced in chat, generate embedding, and wire into graph."""
    try:
        return await service.ingest_paper(input_data)
    except EnhancementToolError as exc:
        logger.warning("EnhancementToolError in ingest_paper_endpoint: %s", exc.message)
        raise HTTPException(status_code=get_http_status_code(exc), detail=exc.to_dict()) from exc
    except Exception as exc:
        logger.exception("Unexpected error in ingest_paper_endpoint: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/confirm-title", response_model=ConfirmTitleIngestionOutput)
async def confirm_title_endpoint(
    input_data: ConfirmTitleIngestionInput,
    service: IngestionServiceDep,
) -> ConfirmTitleIngestionOutput:
    """Handle interactive user confirmation chip click for free-text titles."""
    try:
        return await service.confirm_title_chip(input_data)
    except EnhancementToolError as exc:
        logger.warning("EnhancementToolError in confirm_title_endpoint: %s", exc.message)
        raise HTTPException(status_code=get_http_status_code(exc), detail=exc.to_dict()) from exc
    except Exception as exc:
        logger.exception("Unexpected error in confirm_title_endpoint: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
