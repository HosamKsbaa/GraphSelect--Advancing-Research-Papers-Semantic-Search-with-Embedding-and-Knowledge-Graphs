"""Search and streaming API endpoints for ALRS v2."""
from __future__ import annotations

import asyncio
import json
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
from models.progress import EventType, ProgressEvent, CycleResultsData

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

        # Link paper to session at depth 0
        await neo4j_service.execute_write(
            """MERGE (s:Session {session_id: $session_id})
               WITH s
               MATCH (p:Paper {doi: $doi})
               MERGE (s)-[:CONTAINS {depth: 0}]->(p)""",
            {"session_id": session_id, "doi": paper.doi},
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
    """Stream SSE events during BFS crawl for the given session.

    This is the main entry point that runs the actual BFS cycle.
    The client connects via EventSource and receives real-time progress.
    """
    from main import neo4j_service, mysql_service
    from config import get_settings

    if neo4j_service is None or mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database services not initialized",
        )

    # Fetch session from MySQL
    session_data = await mysql_service.get_session(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Generate SSE events during search execution."""
        from services.openalex_service import OpenAlexService
        from services.gemini_service import GeminiService
        from services.rate_limiter import AdaptiveRateLimiter
        from services.graph_search_service import GraphSearchService

        settings = get_settings()

        # Initialize services
        openalex = OpenAlexService(api_key=settings.openalex_api_key)
        gemini = GeminiService(
            api_key=settings.gemini_api_key,
            output_dimensionality=settings.embedding_dimensions,
        )
        rate_limiter = AdaptiveRateLimiter(
            initial_rate=settings.openalex_rate_limit,
        )

        bfs = GraphSearchService(
            neo4j=neo4j_service,
            openalex=openalex,
            gemini=gemini,
            rate_limiter=rate_limiter,
        )

        # Parse session data
        seed_doi: str = session_data["seed_doi"]
        research_questions: list[str] = json.loads(session_data["research_questions"]) if isinstance(session_data["research_questions"], str) else session_data["research_questions"]
        similarity_threshold: float = float(session_data["similarity_threshold"])
        max_depth: int = int(session_data["max_depth"])
        mode: str = session_data["mode"]

        # Emit search_started
        event = ProgressEvent(
            event_type=EventType.SEARCH_STARTED,
            session_id=session_id,
            progress_percent=0.0,
            message=f"Starting BFS crawl from seed paper: {seed_doi}",
            data={"seed_doi": seed_doi, "max_depth": max_depth, "mode": mode},
        )
        yield {
            "event": event.event_type.value,
            "data": event.model_dump_json(),
        }

        # Update session to RUNNING
        await mysql_service.update_session_status(session_id, SessionStatus.RUNNING.value)

        try:
            queued_dois = [seed_doi]
            total_discovered = 0

            for depth in range(max_depth):
                if not queued_dois:
                    break

                progress_base = (depth / max_depth) * 80  # 80% allocated to crawling

                # Run BFS cycle for this level
                cycle_msg = f"Level {depth + 1}/{max_depth}: crawling {len(queued_dois)} papers..."
                yield {
                    "event": "progress",
                    "data": ProgressEvent(
                        event_type=EventType.LEVEL_COMPLETE,
                        session_id=session_id,
                        progress_percent=progress_base,
                        message=cycle_msg,
                        data={"depth": depth, "queue_size": len(queued_dois)},
                    ).model_dump_json(),
                }

                cycle_result = await bfs.run_bfs_cycle(
                    session_id=session_id,
                    queued_dois=queued_dois,
                    current_depth=depth + 1,
                    max_depth=max_depth,
                )

                total_discovered += cycle_result.papers_discovered

                # Emit level complete
                level_event = ProgressEvent(
                    event_type=EventType.LEVEL_COMPLETE,
                    session_id=session_id,
                    progress_percent=progress_base + (40 / max_depth),
                    message=f"Level {depth + 1} complete: {cycle_result.papers_discovered} papers found, {cycle_result.papers_new} new",
                    data={
                        "depth": depth + 1,
                        "papers_discovered": cycle_result.papers_discovered,
                        "papers_new": cycle_result.papers_new,
                    },
                )
                yield {
                    "event": level_event.event_type.value,
                    "data": level_event.model_dump_json(),
                }

                # Update session progress
                await mysql_service.update_session_progress(
                    session_id,
                    papers_discovered=total_discovered,
                    current_depth=depth + 1,
                )

                # Embed new papers
                if cycle_result.papers_new > 0:
                    embed_msg = f"Embedding {cycle_result.papers_new} new papers..."
                    yield {
                        "event": "progress",
                        "data": ProgressEvent(
                            event_type=EventType.EMBEDDING_PROGRESS,
                            session_id=session_id,
                            progress_percent=progress_base + (60 / max_depth),
                            message=embed_msg,
                        ).model_dump_json(),
                    }

                    # Get unembedded DOIs from Neo4j for this session
                    unembedded = await neo4j_service.get_unembedded_dois(session_id)
                    embedded_count = await bfs.embed_papers(unembedded)

                    yield {
                        "event": EventType.EMBEDDING_PROGRESS.value,
                        "data": ProgressEvent(
                            event_type=EventType.EMBEDDING_PROGRESS,
                            session_id=session_id,
                            progress_percent=progress_base + (70 / max_depth),
                            message=f"Embedded {embedded_count} papers",
                            data={"embedded_count": embedded_count},
                        ).model_dump_json(),
                    }

                # Determine next queue
                if mode == SearchMode.AUTOMATED.value:
                    queued_dois = cycle_result.new_dois
                else:
                    # Interactive mode: emit cycle results and stop
                    cycle_data = CycleResultsData(
                        level=depth + 1,
                        papers_discovered=cycle_result.papers_discovered,
                        papers_new=cycle_result.papers_new,
                    )
                    yield {
                        "event": EventType.CYCLE_RESULTS.value,
                        "data": ProgressEvent(
                            event_type=EventType.CYCLE_RESULTS,
                            session_id=session_id,
                            progress_percent=progress_base + (80 / max_depth),
                            message=f"Level {depth + 1} results ready. Select papers for next cycle.",
                            data=cycle_data.model_dump(),
                        ).model_dump_json(),
                    }
                    # Pause for interactive — user must call /enqueue
                    await mysql_service.update_session_status(
                        session_id, SessionStatus.PAUSED.value
                    )
                    break

            # Embed research questions
            await bfs.embed_questions(session_id, research_questions)

            yield {
                "event": "progress",
                "data": ProgressEvent(
                    event_type=EventType.EMBEDDING_PROGRESS,
                    session_id=session_id,
                    progress_percent=85.0,
                    message="Research questions embedded",
                ).model_dump_json(),
            }

            # Search complete
            complete_event = ProgressEvent(
                event_type=EventType.SEARCH_COMPLETE,
                session_id=session_id,
                progress_percent=100.0,
                message=f"Search complete! {total_discovered} papers discovered across {max_depth} levels.",
                data={"total_papers": total_discovered},
            )
            yield {
                "event": complete_event.event_type.value,
                "data": complete_event.model_dump_json(),
            }

            if mode == SearchMode.AUTOMATED.value:
                await mysql_service.update_session_status(
                    session_id, SessionStatus.COMPLETED.value
                )

        except Exception as e:
            logger.exception("Search failed for session %s", session_id)
            await mysql_service.update_session_status(
                session_id, SessionStatus.FAILED.value
            )
            fail_event = ProgressEvent(
                event_type=EventType.SEARCH_FAILED,
                session_id=session_id,
                progress_percent=0.0,
                message=f"Search failed: {str(e)}",
            )
            yield {
                "event": fail_event.event_type.value,
                "data": fail_event.model_dump_json(),
            }
        finally:
            await openalex.close()

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
    from main import mysql_service

    if mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not initialized",
        )

    if not dois:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one DOI must be provided",
        )

    # Verify session exists and is paused
    session = await mysql_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Store enqueued DOIs for next cycle
    await mysql_service.execute(
        """UPDATE sessions
           SET full_state = JSON_SET(COALESCE(full_state, '{}'), '$.enqueued_dois', %s),
               status = 'running'
           WHERE session_id = %s""",
        (json.dumps(dois), session_id),
    )

    return {
        "session_id": session_id,
        "enqueued": len(dois),
        "dois": dois,
        "message": f"Enqueued {len(dois)} papers for next cycle",
    }
