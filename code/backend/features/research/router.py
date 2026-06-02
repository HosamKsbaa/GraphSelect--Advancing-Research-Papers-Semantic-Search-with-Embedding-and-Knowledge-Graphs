"""Research domain REST endpoints.

Thin router that delegates to :mod:`features.research.service`.

Endpoints:
    POST /{project_id}/questions       → add_research_question
    GET  /{project_id}/questions       → list_research_questions
    GET  /{project_id}/top-authors     → get_top_authors
    GET  /{project_id}/top-venues      → get_top_venues
    GET  /search/author                → search_by_author
    GET  /search/venue                 → search_by_venue
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from core.dependencies import (
    get_embedding_provider,
    get_neo4j_service,
    get_openalex_service,
)
from features.research import service as research_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# ── Request / response models ────────────────────────────────────────


class AddQuestionBody(BaseModel):
    """Body for the add-research-question endpoint."""

    question_text: str = Field(..., min_length=5, description="The research question text.")


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/{project_id}/questions")
async def add_research_question_endpoint(
    project_id: str,
    body: AddQuestionBody,
    request: Request,
) -> dict[str, Any]:
    """Add a new research question to a project."""
    from core.db.neo4j_service import Neo4jService
    from features.embedding.providers.base import EmbeddingProvider

    neo4j: Neo4jService = getattr(request.app.state, "neo4j_service", None)  # type: ignore[assignment]
    if neo4j is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j not initialized")

    # Build embedding provider from settings
    from config import get_settings
    from core.logging.log_service import LogService
    from core.db.mysql_service import MySQLService
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider

    settings = get_settings()
    mysql: MySQLService | None = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None  # type: ignore[arg-type]
    embedding_provider: EmbeddingProvider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        log_service=log_service,
        model_name=settings.embedding_model,
    )

    try:
        return await research_svc.add_research_question(
            project_id=project_id,
            question_text=body.question_text,
            neo4j=neo4j,
            embedding_provider=embedding_provider,
        )
    except Exception as exc:
        logger.exception("add_research_question_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/questions")
async def list_research_questions_endpoint(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """List all research questions for a project."""
    from core.db.neo4j_service import Neo4jService

    neo4j: Neo4jService = getattr(request.app.state, "neo4j_service", None)  # type: ignore[assignment]
    if neo4j is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j not initialized")

    try:
        return await research_svc.list_research_questions(project_id=project_id, neo4j=neo4j)
    except Exception as exc:
        logger.exception("list_research_questions_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/top-authors")
async def get_top_authors_endpoint(
    project_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Retrieve the top authors of papers in the project."""
    from core.db.neo4j_service import Neo4jService

    neo4j: Neo4jService = getattr(request.app.state, "neo4j_service", None)  # type: ignore[assignment]
    if neo4j is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j not initialized")

    try:
        return await research_svc.get_top_authors(project_id=project_id, limit=limit, neo4j=neo4j)
    except Exception as exc:
        logger.exception("get_top_authors_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/top-venues")
async def get_top_venues_endpoint(
    project_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Retrieve the top venues of papers in the project."""
    from core.db.neo4j_service import Neo4jService

    neo4j: Neo4jService = getattr(request.app.state, "neo4j_service", None)  # type: ignore[assignment]
    if neo4j is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j not initialized")

    try:
        return await research_svc.get_top_venues(project_id=project_id, limit=limit, neo4j=neo4j)
    except Exception as exc:
        logger.exception("get_top_venues_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/search/author")
async def search_by_author_endpoint(
    request: Request,
    name: str = Query(..., description="Author name to search for"),
    max_results: int = Query(default=10, ge=1, le=25),
) -> dict[str, Any]:
    """Search OpenAlex for papers by a specific author."""
    from config import get_settings
    from core.clients.openalex_client import OpenAlexService
    from core.logging.log_service import LogService
    from core.db.mysql_service import MySQLService

    settings = get_settings()
    mysql: MySQLService | None = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None  # type: ignore[arg-type]
    openalex = OpenAlexService(api_key=settings.openalex_api_key, log_service=log_service)

    try:
        return await research_svc.search_by_author(
            author_name=name,
            max_results=max_results,
            openalex=openalex,
        )
    except Exception as exc:
        logger.exception("search_by_author_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        await openalex.close()


@router.get("/search/venue")
async def search_by_venue_endpoint(
    request: Request,
    name: str = Query(..., description="Venue name to search for"),
    max_results: int = Query(default=10, ge=1, le=25),
) -> dict[str, Any]:
    """Search OpenAlex for papers published in a specific venue."""
    from config import get_settings
    from core.clients.openalex_client import OpenAlexService
    from core.logging.log_service import LogService
    from core.db.mysql_service import MySQLService

    settings = get_settings()
    mysql: MySQLService | None = getattr(request.app.state, "mysql_service", None)
    log_service = LogService(mysql) if mysql else None  # type: ignore[arg-type]
    openalex = OpenAlexService(api_key=settings.openalex_api_key, log_service=log_service)

    try:
        return await research_svc.search_by_venue(
            venue_name=name,
            max_results=max_results,
            openalex=openalex,
        )
    except Exception as exc:
        logger.exception("search_by_venue_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        await openalex.close()
