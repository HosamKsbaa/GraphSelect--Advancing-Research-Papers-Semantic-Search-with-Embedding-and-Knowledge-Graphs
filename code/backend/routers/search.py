"""Search and streaming API endpoints for ALRS v2."""
from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from models.paper import PaperSummary
from models.session import (
    SearchMode,
    SearchRequest,
    SearchResponse,
    SessionStatus,
)
from models.progress import EventType, ProgressEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/resolve-title", response_model=list[PaperSummary])
async def resolve_title(title: str, max_results: int = 10) -> list[PaperSummary]:
    """Search for papers by title, returning a candidate list.

    The researcher selects one of these candidates as the seed paper.
    """
    from main import neo4j_service, mysql_service
    from config import get_settings
    from services.openalex_service import OpenAlexService

    settings = get_settings()
    openalex = OpenAlexService(api_key=settings.openalex_api_key)
    try:
        candidates = await openalex.search_by_title(title, max_results)
        return candidates
    finally:
        await openalex.close()


@router.post("/start", response_model=SearchResponse)
async def start_search(request: SearchRequest) -> SearchResponse:
    """Start a new literature review search session.

    Creates a MySQL session, resolves the seed paper, stores in Neo4j,
    and returns a session_id for streaming/enqueue operations.
    """
    from main import neo4j_service, mysql_service
    from config import get_settings
    from services.openalex_service import OpenAlexService

    if neo4j_service is None or mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database services not initialized",
        )

    settings = get_settings()

    # Resolve seed paper DOI
    seed_doi = request.seed_doi
    if seed_doi is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_doi is required. Use /resolve-title to search by title first.",
        )

    # Create session in MySQL
    session_id = str(uuid.uuid4())
    import json

    await mysql_service.execute(
        """INSERT INTO sessions
           (session_id, seed_doi, research_questions, similarity_threshold,
            max_depth, mode, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            session_id,
            seed_doi,
            json.dumps(request.research_questions),
            request.similarity_threshold,
            request.max_depth,
            request.mode.value,
            SessionStatus.CREATED.value,
        ),
    )

    # Fetch seed paper from OpenAlex and store in Neo4j
    openalex = OpenAlexService(api_key=settings.openalex_api_key)
    try:
        paper = await openalex.get_paper_by_doi(seed_doi, session_id=session_id)
        if paper is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper not found in OpenAlex: {seed_doi}",
            )

        # Store in Neo4j
        await neo4j_service.execute_write(
            """MERGE (p:Paper {doi: $doi})
               SET p.title = $title,
                   p.abstract = $abstract,
                   p.year = $year,
                   p.cited_by_count = $cited_by_count,
                   p.openalex_id = $openalex_id,
                   p.publication_date = $publication_date,
                   p.source = $source,
                   p.is_seed = true""",
            {
                "doi": paper.doi,
                "title": paper.title,
                "abstract": paper.abstract,
                "year": paper.year,
                "cited_by_count": paper.cited_by_count,
                "openalex_id": paper.openalex_id,
                "publication_date": paper.publication_date,
                "source": paper.source,
            },
        )
    finally:
        await openalex.close()

    return SearchResponse(
        session_id=session_id,
        status=SessionStatus.CREATED,
        seed_paper_doi=seed_doi,
        message=f"Session created. Seed paper '{paper.title}' stored in graph.",
    )


@router.get("/{session_id}/stream")
async def stream_search(session_id: str) -> EventSourceResponse:
    """Stream SSE events during BFS crawl for the given session."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Generate SSE events during search execution."""
        import json
        from datetime import datetime

        # Emit search_started event
        event = ProgressEvent(
            event_type=EventType.SEARCH_STARTED,
            session_id=session_id,
            progress_percent=0.0,
            message="Search started",
        )
        yield {
            "event": event.event_type.value,
            "data": event.model_dump_json(),
        }

        # TODO: Implement actual BFS cycle execution here
        # For now, emit a placeholder search_complete event
        complete_event = ProgressEvent(
            event_type=EventType.SEARCH_COMPLETE,
            session_id=session_id,
            progress_percent=100.0,
            message="Search complete (placeholder — BFS not yet wired)",
        )
        yield {
            "event": complete_event.event_type.value,
            "data": complete_event.model_dump_json(),
        }

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/enqueue")
async def enqueue_papers(
    session_id: str,
    dois: list[str],
) -> dict[str, object]:
    """Accept researcher's paper selections for the next BFS cycle.

    In interactive mode, the researcher reviews top papers from each
    cycle and selects which ones to crawl deeper.
    """
    if not dois:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one DOI must be provided",
        )

    # TODO: Store in queue for next BFS cycle
    return {
        "session_id": session_id,
        "enqueued": len(dois),
        "dois": dois,
        "message": f"Enqueued {len(dois)} papers for next cycle",
    }
