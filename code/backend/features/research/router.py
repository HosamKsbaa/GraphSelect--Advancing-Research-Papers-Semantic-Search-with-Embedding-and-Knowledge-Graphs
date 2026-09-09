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
from pydantic import BaseModel, Field, model_validator

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

    question_text: str = Field(default="", description="The research question text.")
    text: str | None = Field(default=None, description="Alternative field name for research question text.")

    @model_validator(mode="before")
    @classmethod
    def unify_question_text(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("question_text") or data.get("text") or ""
            val_str = str(val).strip()
            if not val_str:
                raise ValueError("Research question text is required and cannot be empty.")
            data["question_text"] = val_str
            data["text"] = val_str
        elif isinstance(data, str):
            val_str = data.strip()
            if not val_str:
                raise ValueError("Research question text is required and cannot be empty.")
            data = {"question_text": val_str, "text": val_str}
        return data


class DecomposeQueryRequest(BaseModel):
    """Body for the autonomous query decomposition endpoint."""

    topic: str = Field(..., min_length=3, description="High-level research topic or prompt string.")
    num_questions: int = Field(default=4, ge=3, le=5, description="Target number of sub-questions (3-5).")
    auto_save: bool = Field(default=False, description="Automatically persist questions to project.")



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
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider

    settings = get_settings()
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)
    embedding_provider: EmbeddingProvider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        log_service=log_service,
        model_name=settings.embedding_model,
    )

    try:
        res = await research_svc.add_research_question(
            project_id=project_id,
            question_text=body.question_text,
            neo4j=neo4j,
            embedding_provider=embedding_provider,
        )
        res["question"] = {
            "question_id": res.get("question_id"),
            "id": res.get("question_id"),
            "text": res.get("text"),
            "question_text": res.get("text"),
        }
        return res
    except Exception as exc:
        logger.exception("add_research_question_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{project_id}/decompose-query")
async def decompose_query_endpoint(
    project_id: str,
    body: DecomposeQueryRequest,
    request: Request,
) -> dict[str, Any]:
    """Decompose a high-level research prompt/topic into domain-specific sub-questions."""
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
    from config import get_settings
    from core.logging.log_service import LogService

    settings = get_settings()
    neo4j: Neo4jService | None = getattr(request.app.state, "neo4j_service", None)
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)

    llm = LLMService(
        api_key=settings.gemini_api_key,
        model_name=settings.adk_model_name,
        log_service=log_service,
    )
    embedding_provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        log_service=log_service,
        model_name=settings.embedding_model,
    )

    try:
        return await research_svc.decompose_query(
            project_id=project_id,
            topic=body.topic,
            num_questions=body.num_questions,
            auto_save=body.auto_save,
            llm=llm,
            neo4j=neo4j,
            embedding_provider=embedding_provider,
        )
    except Exception as exc:
        logger.exception("decompose_query_endpoint failed")
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

    settings = get_settings()
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)
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

    settings = get_settings()
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)
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
