"""Search and streaming API endpoints for ALRS v2 backed by Neo4j."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.clients.openalex_client import OpenAlexService
from core.db.neo4j_service import Neo4jService
from core.dependencies import (
    get_graph_search_service,
    get_neo4j_service,
    get_openalex_service,
    get_search_session_service,
)
from features.ranking.models import GroupedResults
from features.retrieval.models import PaperSummary
from features.search.graph_search_service import GraphSearchService
from features.search.session_service import SearchSessionService
from features.sessions.models import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


# ── Request models (endpoint-specific) ───────────────────────────────

class RerankRequest(BaseModel):
    """Body for the re-rank endpoint: new threshold and weight split."""

    similarity_threshold: float = Field(..., ge=0.0, le=1.0)
    similarity_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    pagerank_weight: float = Field(default=0.3, ge=0.0, le=1.0)


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/resolve-title", response_model=list[PaperSummary])
async def resolve_title(
    title: str,
    max_results: int = 10,
    openalex: OpenAlexService = Depends(get_openalex_service),
) -> list[PaperSummary]:
    """Search for papers by title, returning a candidate list."""
    try:
        return await openalex.search_by_title(title, max_results)
    except Exception as exc:
        logger.exception("Failed to resolve title: %s", title)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OpenAlex error: {exc}",
        )


@router.post("/start", response_model=SearchResponse)
async def start_search(
    request: SearchRequest,
    session_svc: SearchSessionService = Depends(get_search_session_service),
) -> SearchResponse:
    """Create a new literature-review search session in Neo4j."""
    try:
        return await session_svc.create_session(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.get("/{session_id}/stream")
async def stream_search(
    session_id: str,
    request: Request,
) -> EventSourceResponse:
    """Stream BFS progress events as Server-Sent Events (SSE)."""
    neo4j_service: Neo4jService | None = getattr(
        request.app.state, "neo4j_service", None
    )

    if neo4j_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    stream_svc = SearchSessionService(
        neo4j=neo4j_service,
        openalex=OpenAlexService.__new__(OpenAlexService),
    )
    session_data = await stream_svc.get_session(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    return EventSourceResponse(
        stream_svc.build_search_stream(
            session_id=session_id,
            session_data=session_data,
            neo4j_service=neo4j_service,
        )
    )


@router.post("/{session_id}/enqueue")
async def enqueue_papers(
    session_id: str,
    dois: list[str],
    session_svc: SearchSessionService = Depends(get_search_session_service),
) -> dict[str, object]:
    """Accept researcher's DOI selections for the next BFS cycle."""
    if not dois:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one DOI must be provided",
        )

    try:
        return await session_svc.enqueue_papers(session_id, dois)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get("/{session_id}/results", response_model=GroupedResults)
async def get_results(
    session_id: str,
    similarity_weight: float = 0.7,
    pagerank_weight: float = 0.3,
    bfs: GraphSearchService = Depends(get_graph_search_service),
) -> GroupedResults:
    """Get ranked and grouped results for a completed session."""
    try:
        return await bfs.rank_papers(
            session_id=session_id,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post("/{session_id}/rerank", response_model=GroupedResults)
async def rerank_results(
    session_id: str,
    request: RerankRequest,
    neo4j: Neo4jService = Depends(get_neo4j_service),
    bfs: GraphSearchService = Depends(get_graph_search_service),
) -> GroupedResults:
    """Adjust similarity threshold and weight split, then re-rank."""
    await neo4j.execute_write(
        """MATCH (c:ResearchCampaign)
           WHERE c.campaign_id = $session_id OR c.session_id = $session_id
           SET c.similarity_threshold = $threshold, c.updated_at = datetime()""",
        {"session_id": session_id, "threshold": request.similarity_threshold},
    )

    try:
        return await bfs.rank_papers(
            session_id=session_id,
            similarity_weight=request.similarity_weight,
            pagerank_weight=request.pagerank_weight,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
