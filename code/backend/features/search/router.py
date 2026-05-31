"""Search and streaming API endpoints for ALRS v2.

This router is deliberately *thin* — it validates HTTP input, delegates
to the appropriate service, and translates service exceptions into HTTP
error responses.  All business logic lives in:

    - :class:`~features.search.session_service.SearchSessionService`
      (session CRUD + SSE stream factory)
    - :class:`~features.search.graph_search_service.GraphSearchService`
      (BFS orchestration + ranking)

Endpoints:
    POST /api/search/resolve-title   → candidate paper list from OpenAlex
    POST /api/search/start           → create session + persist seed paper
    GET  /api/search/{id}/stream     → SSE stream of BFS progress events
    POST /api/search/{id}/enqueue    → accept DOIs for next BFS cycle
    GET  /api/search/{id}/results    → ranked & grouped results
    POST /api/search/{id}/rerank     → adjust weights and re-rank
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status, Depends, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

from features.retrieval.models import PaperSummary
from features.sessions.models import SearchRequest, SearchResponse
from features.ranking.models import GroupedResults

from core.db.neo4j_service import Neo4jService
from core.db.mysql_service import MySQLService
from core.clients.openalex_client import OpenAlexService
from features.search.graph_search_service import GraphSearchService
from features.search.session_service import SearchSessionService

from core.dependencies import (
    get_neo4j_service,
    get_mysql_service,
    get_openalex_service,
    get_graph_search_service,
    get_search_session_service,
)

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
    """Search for papers by title, returning a candidate list.

    The frontend calls this so the user can pick the correct seed
    paper before starting a session.
    """
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
    """Create a new literature-review search session.

    Delegates entirely to ``SearchSessionService.create_session()``
    which handles MySQL INSERT, OpenAlex fetch, and Neo4j MERGE.
    """
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get("/{session_id}/stream")
async def stream_search(
    session_id: str,
    request: Request,
) -> EventSourceResponse:
    """Stream SSE events during the BFS crawl for a given session.

    This endpoint cannot use standard DI for the stream because the
    SSE generator must outlive the request scope.  Instead, it reads
    the service singletons from ``app.state`` and passes them to
    ``SearchSessionService.build_search_stream()``.
    """
    # Retrieve singletons from app state (not DI — stream outlives request)
    neo4j_service: Neo4jService | None = getattr(
        request.app.state, "neo4j_service", None
    )
    mysql_service: MySQLService | None = getattr(
        request.app.state, "mysql_service", None
    )

    if neo4j_service is None or mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database services not initialized",
        )

    # Validate session exists
    session_data = await mysql_service.get_session(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Delegate stream construction to the service layer
    stream_svc = SearchSessionService(
        neo4j=neo4j_service,
        mysql=mysql_service,
        openalex=OpenAlexService.__new__(OpenAlexService),  # placeholder — stream builds its own
    )

    return EventSourceResponse(
        stream_svc.build_search_stream(
            session_id=session_id,
            session_data=session_data,
            neo4j_service=neo4j_service,
            mysql_service=mysql_service,
        )
    )


@router.post("/{session_id}/enqueue")
async def enqueue_papers(
    session_id: str,
    dois: list[str],
    session_svc: SearchSessionService = Depends(get_search_session_service),
) -> dict[str, object]:
    """Accept researcher's DOI selections for the next BFS cycle.

    Validates input, then delegates to
    ``SearchSessionService.enqueue_papers()``.
    """
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
    """Get ranked and grouped results for a completed session.

    Delegates to ``GraphSearchService.rank_papers()`` which computes
    the composite score (semantic similarity × weight + PageRank × weight).
    """
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
    mysql: MySQLService = Depends(get_mysql_service),
    bfs: GraphSearchService = Depends(get_graph_search_service),
) -> GroupedResults:
    """Adjust similarity threshold and weight split, then re-rank.

    Persists the new threshold to MySQL so it survives page refreshes,
    then delegates ranking to ``GraphSearchService.rank_papers()``.
    """
    # Persist the new threshold
    await mysql.execute(
        """UPDATE sessions
           SET similarity_threshold = %s
           WHERE session_id = %s""",
        (request.similarity_threshold, session_id),
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
