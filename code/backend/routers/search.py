"""Search and streaming API endpoints for ALRS v2."""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, status, Depends, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

from models.paper import PaperSummary
from models.session import (
    SearchMode,
    SearchRequest,
    SearchResponse,
    SessionStatus,
)
from models.progress import EventType, ProgressEvent
from models.ranked_paper import GroupedResults

from db.neo4j_service import Neo4jService
from db.mysql_service import MySQLService
from services.openalex_service import OpenAlexService
from services.graph_search_service import GraphSearchService

from dependencies import (
    get_neo4j_service,
    get_mysql_service,
    get_openalex_service,
    get_graph_search_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/resolve-title", response_model=list[PaperSummary])
async def resolve_title(
    title: str,
    max_results: int = 10,
    openalex: OpenAlexService = Depends(get_openalex_service)
) -> list[PaperSummary]:
    """Search for papers by title, returning a candidate list."""
    candidates = await openalex.search_by_title(title, max_results)
    return candidates


@router.post("/start", response_model=SearchResponse)
async def start_search(
    request: SearchRequest,
    mysql: MySQLService = Depends(get_mysql_service),
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
) -> SearchResponse:
    """Start a new literature review search session."""
    seed_doi = request.seed_doi
    if seed_doi is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_doi is required. Use /resolve-title to search by title first.",
        )

    session_id = str(uuid.uuid4())

    await mysql.execute(
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

    paper = await openalex.get_paper_by_doi(seed_doi, session_id=session_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found in OpenAlex: {seed_doi}",
        )

    await neo4j.execute_write(
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

    await neo4j.execute_write(
        """MERGE (s:Session {session_id: $session_id})
           WITH s
           MATCH (p:Paper {doi: $doi})
           MERGE (s)-[:CONTAINS {depth: 0}]->(p)""",
        {"session_id": session_id, "doi": paper.doi},
    )

    return SearchResponse(
        session_id=session_id,
        status=SessionStatus.CREATED,
        seed_paper_doi=seed_doi,
        message=f"Session created. Seed paper '{paper.title}' stored in graph.",
    )


@router.get("/{session_id}/stream")
async def stream_search(
    session_id: str,
    request: Request,
) -> EventSourceResponse:
    """Stream SSE events during BFS crawl for the given session."""
    neo4j_service: Neo4jService | None = getattr(request.app.state, "neo4j_service", None)
    mysql_service: MySQLService | None = getattr(request.app.state, "mysql_service", None)

    if neo4j_service is None or mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database services not initialized",
        )

    session_data = await mysql_service.get_session(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        from services.openalex_service import OpenAlexService
        from services.gemini_service import GeminiService
        from services.rate_limiter import AdaptiveRateLimiter
        from services.graph_search_service import GraphSearchService
        from services.crawler_service import CrawlerService
        from services.ranking_service import RankingService
        from services.log_service import LogService
        from config import get_settings

        settings = get_settings()

        log_service = LogService(mysql_service)
        openalex = OpenAlexService(
            api_key=settings.openalex_api_key,
            log_service=log_service,
        )
        gemini = GeminiService(
            api_key=settings.gemini_api_key,
            output_dimensionality=settings.embedding_dimensions,
            log_service=log_service,
            model_name=settings.embedding_model,
        )
        rate_limiter = AdaptiveRateLimiter(
            initial_rate=settings.openalex_rate_limit,
        )
        crawler = CrawlerService(neo4j_service, openalex, rate_limiter, log_service)
        ranking = RankingService(neo4j_service, mysql_service)

        bfs = GraphSearchService(
            neo4j=neo4j_service,
            openalex=openalex,
            gemini=gemini,
            crawler=crawler,
            ranking=ranking,
            rate_limiter=rate_limiter,
            log_service=log_service,
        )

        seed_doi: str = session_data["seed_doi"]
        research_questions: list[str] = json.loads(session_data["research_questions"]) if isinstance(session_data["research_questions"], str) else session_data["research_questions"]
        similarity_threshold: float = float(session_data["similarity_threshold"])
        max_depth: int = int(session_data["max_depth"])
        mode: str = session_data["mode"]
        
        raw_state = session_data.get("full_state", "{}")
        full_state = json.loads(raw_state) if raw_state else {}
        queued_dois = full_state.get("enqueued_dois", [seed_doi])

        await mysql_service.update_session_status(session_id, SessionStatus.RUNNING.value)

        try:
            async for evt in bfs.run_full_search(
                session_id=session_id,
                seed_doi=seed_doi,
                research_questions=research_questions,
                similarity_threshold=similarity_threshold,
                max_depth=max_depth,
                mode=mode,
                queued_dois=queued_dois,
            ):
                yield {
                    "event": evt.event_type.value,
                    "data": evt.model_dump_json(),
                }
                
                if evt.event_type == EventType.LEVEL_COMPLETE and evt.data and "papers_discovered" in evt.data:
                    await mysql_service.update_session_progress(
                        session_id,
                        papers_discovered=evt.data.get("papers_discovered", 0), # type: ignore
                        current_depth=evt.data.get("level", 0), # type: ignore
                    )

            if mode == SearchMode.AUTOMATED.value:
                await mysql_service.update_session_status(
                    session_id, SessionStatus.COMPLETED.value
                )
            else:
                await mysql_service.update_session_status(
                    session_id, SessionStatus.PAUSED.value
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
    mysql: MySQLService = Depends(get_mysql_service),
) -> dict[str, object]:
    """Accept researcher's paper selections for the next BFS cycle."""
    if not dois:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one DOI must be provided",
        )

    session = await mysql.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    await mysql.execute(
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


class RerankRequest(BaseModel):
    similarity_threshold: float = Field(..., ge=0.0, le=1.0)
    similarity_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    pagerank_weight: float = Field(default=0.3, ge=0.0, le=1.0)


@router.get("/{session_id}/results", response_model=GroupedResults)
async def get_results(
    session_id: str,
    similarity_weight: float = 0.7,
    pagerank_weight: float = 0.3,
    bfs: GraphSearchService = Depends(get_graph_search_service),
) -> GroupedResults:
    """Get ranked and grouped results for a given session."""
    try:
        results = await bfs.rank_papers(
            session_id=session_id,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
        )
        return results
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
    """Adjust similarity threshold and weights, update MySQL config, and re-rank."""
    await mysql.execute(
        """UPDATE sessions
           SET similarity_threshold = %s
           WHERE session_id = %s""",
        (request.similarity_threshold, session_id),
    )

    try:
        results = await bfs.rank_papers(
            session_id=session_id,
            similarity_weight=request.similarity_weight,
            pagerank_weight=request.pagerank_weight,
        )
        return results
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
