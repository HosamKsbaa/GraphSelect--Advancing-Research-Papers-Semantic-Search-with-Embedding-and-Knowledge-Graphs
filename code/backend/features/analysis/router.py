"""Analysis domain REST endpoints.

Thin router that delegates to :mod:`features.analysis.service`.

Endpoints:
    GET   /{project_id}/similarity/{doi}  → compute_paper_similarity
    GET   /{project_id}/citation-stats    → get_citation_stats
    GET   /{project_id}/coverage          → analyze_coverage
    POST  /{project_id}/gap-queries       → suggest_gap_queries
    GET   /{project_id}/ranked-papers     → rank_papers
    POST  /{project_id}/synthesize        → synthesize_evidence_endpoint
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, status

from features.analysis import service as analysis_svc
from features.analysis.models import (
    GapQueriesBody,
    SynthesisRequest,
    SynthesisResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ── Helper ───────────────────────────────────────────────────────────


def _get_neo4j(request: Request) -> Any:
    """Extract Neo4j service from app state or raise 503."""
    neo4j = getattr(request.app.state, "neo4j_service", None)
    if neo4j is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )
    return neo4j


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/{project_id}/similarity/{doi:path}")
async def compute_paper_similarity_endpoint(
    project_id: str,
    doi: str,
    request: Request,
) -> dict[str, Any]:
    """Compute cosine similarity between a paper and project research questions."""
    neo4j = _get_neo4j(request)
    try:
        return await analysis_svc.compute_paper_similarity(
            project_id=project_id, doi=doi, neo4j=neo4j,
        )
    except Exception as exc:
        logger.exception("compute_paper_similarity_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/citation-stats")
async def get_citation_stats_endpoint(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Get aggregate citation and similarity statistics for the project."""
    neo4j = _get_neo4j(request)
    try:
        return await analysis_svc.get_citation_stats(project_id=project_id, neo4j=neo4j)
    except Exception as exc:
        logger.exception("get_citation_stats_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/coverage")
async def analyze_coverage_endpoint(
    project_id: str,
    request: Request,
    threshold: float = Query(default=0.6, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Analyze how well the paper library covers each research question."""
    neo4j = _get_neo4j(request)
    try:
        return await analysis_svc.analyze_coverage(
            project_id=project_id, threshold=threshold, neo4j=neo4j,
        )
    except Exception as exc:
        logger.exception("analyze_coverage_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{project_id}/gap-queries")
async def suggest_gap_queries_endpoint(
    project_id: str,
    body: GapQueriesBody,
    request: Request,
) -> dict[str, Any]:
    """Generate search queries to fill a coverage gap using the LLM."""
    # Build LLM service from settings
    from config import get_settings
    from core.llm.service import LLMService
    from core.logging.log_service import LogService

    settings = get_settings()
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)
    llm = LLMService(
        api_key=settings.gemini_api_key,
        model_name=settings.adk_model_name,
        log_service=log_service,
    )

    try:
        return await analysis_svc.suggest_gap_queries(
            gap_question=body.gap_question,
            max_queries=body.max_queries,
            llm=llm,
        )
    except Exception as exc:
        logger.exception("suggest_gap_queries_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{project_id}/ranked-papers")
async def rank_papers_endpoint(
    project_id: str,
    request: Request,
    similarity_weight: float = Query(default=0.7, ge=0.0, le=1.0),
    pagerank_weight: float = Query(default=0.3, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Rank project papers using a hybrid similarity + PageRank score."""
    neo4j = _get_neo4j(request)
    try:
        return await analysis_svc.rank_papers(
            project_id=project_id,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
            neo4j=neo4j,
        )
    except Exception as exc:
        logger.exception("rank_papers_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{project_id}/synthesize", response_model=SynthesisResponse)
async def synthesize_evidence_endpoint(
    project_id: str,
    request: Request,
    body: SynthesisRequest | None = None,
) -> Any:
    """Synthesize cross-paper literature findings, comparison dimensions, and structured narrative."""
    neo4j = _get_neo4j(request)

    from config import get_settings
    from core.llm.service import LLMService
    from core.logging.log_service import LogService

    settings = get_settings()
    telemetry = getattr(request.app.state, "telemetry_service", None)
    log_service = LogService(telemetry_service=telemetry)
    llm = getattr(request.app.state, "llm_service", None)
    if llm is None:
        llm = LLMService(
            api_key=settings.gemini_api_key,
            model_name=settings.adk_model_name,
            log_service=log_service,
        )

    try:
        dois = body.dois if body and body.dois else None
        rqs = body.research_questions if body and body.research_questions else None
        return await analysis_svc.synthesize_evidence(
            project_id=project_id,
            dois=dois,
            research_questions=rqs,
            neo4j=neo4j,
            llm=llm,
        )
    except Exception as exc:
        logger.exception("synthesize_evidence_endpoint failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
