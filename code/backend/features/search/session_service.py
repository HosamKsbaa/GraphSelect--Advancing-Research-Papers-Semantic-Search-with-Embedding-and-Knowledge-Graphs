"""Search session lifecycle service for ALRS v2 backed by pure Neo4j epistemic graph."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

from core.clients.openalex_client import OpenAlexService
from core.db.neo4j_service import Neo4jService
from features.retrieval.models import PaperSummary
from features.search.models import EventType, ProgressEvent
from features.sessions.models import (
    SearchMode,
    SearchRequest,
    SearchResponse,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class SearchSessionService:
    """Manages the lifecycle of a search session via pure Neo4j persistence."""

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex

    async def create_session(self, request: SearchRequest) -> SearchResponse:
        """Create a new search session node in Neo4j and link the seed paper."""
        seed_doi = request.seed_doi
        if seed_doi is None:
            raise ValueError(
                "seed_doi is required. Use /resolve-title to search by title first."
            )

        session_id = str(uuid.uuid4())

        # Persist session node in Neo4j
        await self._neo4j.execute_write(
            """MERGE (c:ResearchCampaign {campaign_id: $session_id})
               SET c.session_id = $session_id,
                   c.seed_doi = $seed_doi,
                   c.research_questions = $research_questions,
                   c.similarity_threshold = $similarity_threshold,
                   c.max_depth = $max_depth,
                   c.mode = $mode,
                   c.status = $status,
                   c.papers_discovered = 0,
                   c.papers_relevant = 0,
                   c.current_depth = 0,
                   c.created_at = datetime(),
                   c.updated_at = datetime()""",
            {
                "session_id": session_id,
                "seed_doi": seed_doi,
                "research_questions": request.research_questions,
                "similarity_threshold": request.similarity_threshold,
                "max_depth": request.max_depth,
                "mode": request.mode.value,
                "status": SessionStatus.CREATED.value,
            },
        )

        # Fetch seed paper from OpenAlex
        try:
            paper = await self._openalex.get_paper_by_doi(
                seed_doi, session_id=session_id
            )
            if paper is None:
                await self._mark_failed(session_id)
                raise LookupError(f"Paper not found in OpenAlex: {seed_doi}")
        except LookupError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch seed paper %s", seed_doi)
            await self._mark_failed(session_id)
            raise RuntimeError(f"OpenAlex error: {exc}") from exc

        # MERGE seed paper into Neo4j graph and link to Campaign
        await self._neo4j.execute_write(
            """MERGE (p:Paper {doi: $doi})
               SET p.title = $title,
                   p.abstract = $abstract,
                   p.year = $year,
                   p.cited_by_count = $cited_by_count,
                   p.openalex_id = $openalex_id,
                   p.publication_date = $publication_date,
                   p.source = $source,
                   p.is_seed = true
               WITH p
               MATCH (c:ResearchCampaign {campaign_id: $session_id})
               MERGE (c)-[:CONTAINS {depth: 0}]->(p)""",
            {
                "doi": paper.doi,
                "title": paper.title,
                "abstract": paper.abstract,
                "year": paper.year,
                "cited_by_count": paper.cited_by_count,
                "openalex_id": paper.openalex_id,
                "publication_date": paper.publication_date,
                "source": paper.source,
                "session_id": session_id,
            },
        )

        return SearchResponse(
            session_id=session_id,
            status=SessionStatus.CREATED,
            seed_paper_doi=seed_doi,
            message=f"Session created. Seed paper '{paper.title}' stored in graph.",
        )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch session attributes from Neo4j :ResearchCampaign node."""
        records = await self._neo4j.execute_read(
            "MATCH (c:ResearchCampaign) "
            "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
            "RETURN c LIMIT 1",
            {"session_id": session_id},
        )
        if not records:
            return None
        node = records[0].get("c", {})
        props = dict(node) if hasattr(node, "items") else dict(node)
        return props

    async def enqueue_papers(
        self, session_id: str, dois: list[str]
    ) -> dict[str, object]:
        """Store researcher-selected DOIs for next BFS cycle in Neo4j."""
        records = await self._neo4j.execute_write(
            """MATCH (c:ResearchCampaign)
               WHERE c.campaign_id = $session_id OR c.session_id = $session_id
               SET c.enqueued_dois = $dois,
                   c.status = 'running',
                   c.updated_at = datetime()
               RETURN c""",
            {"session_id": session_id, "dois": dois},
        )
        if not records:
            raise LookupError(f"Session not found: {session_id}")

        return {
            "session_id": session_id,
            "enqueued": len(dois),
            "dois": dois,
            "message": f"Enqueued {len(dois)} papers for next cycle",
        }

    async def build_search_stream(
        self,
        session_id: str,
        session_data: dict[str, Any],
        neo4j_service: Neo4jService,
    ) -> AsyncIterator[dict[str, str]]:
        """Build and return an async SSE event generator for a BFS search."""
        from config import get_settings
        from core.clients.rate_limiter import AdaptiveRateLimiter
        from core.logging.log_service import LogService
        from features.embedding.providers.gemini_provider import GeminiService
        from features.ranking.service import RankingService
        from features.search.crawler_service import CrawlerService
        from features.search.graph_search_service import GraphSearchService

        settings = get_settings()
        log_service = LogService()
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
        ranking = RankingService(neo4j_service)

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
        raw_q = session_data.get("research_questions", [])
        research_questions: list[str] = (
            json.loads(raw_q) if isinstance(raw_q, str) else list(raw_q)
        )
        similarity_threshold: float = float(session_data.get("similarity_threshold", 0.5))
        max_depth: int = int(session_data.get("max_depth", 2))
        mode: str = str(session_data.get("mode", "interactive"))
        queued_dois = session_data.get("enqueued_dois", [seed_doi])

        await self._update_session_status(session_id, SessionStatus.RUNNING.value)

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
                if (
                    evt.event_type == EventType.LEVEL_COMPLETE
                    and evt.data
                    and "papers_discovered" in evt.data
                ):
                    await self._update_session_progress(
                        session_id,
                        papers_discovered=int(str(evt.data.get("papers_discovered", 0))),
                        current_depth=int(str(evt.data.get("level", 0))),
                    )

            final_status = (
                SessionStatus.COMPLETED.value
                if mode == SearchMode.AUTOMATED.value
                else SessionStatus.PAUSED.value
            )
            await self._update_session_status(session_id, final_status)

        except asyncio.CancelledError:
            logger.info("Search stream cancelled for session %s", session_id)
            await self._update_session_status(session_id, SessionStatus.PAUSED.value)
            raise
        except Exception as exc:
            logger.exception("Search failed for session %s", session_id)
            await self._update_session_status(session_id, SessionStatus.FAILED.value)
            fail_event = ProgressEvent(
                event_type=EventType.SEARCH_FAILED,
                session_id=session_id,
                progress_percent=0.0,
                message=f"Search failed: {str(exc)}",
            )
            yield {
                "event": fail_event.event_type.value,
                "data": fail_event.model_dump_json(),
            }
        finally:
            await openalex.close()

    async def _mark_failed(self, session_id: str) -> None:
        """Set session status to FAILED in Neo4j."""
        await self._update_session_status(session_id, SessionStatus.FAILED.value)

    async def _update_session_status(self, session_id: str, status: str) -> None:
        """Update campaign session status in Neo4j."""
        await self._neo4j.execute_write(
            "MATCH (c:ResearchCampaign) "
            "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
            "SET c.status = $status, c.updated_at = datetime()",
            {"session_id": session_id, "status": status},
        )

    async def _update_session_progress(
        self, session_id: str, papers_discovered: int, current_depth: int
    ) -> None:
        """Update discovered paper counts and depth in Neo4j."""
        await self._neo4j.execute_write(
            "MATCH (c:ResearchCampaign) "
            "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
            "SET c.papers_discovered = $papers_discovered, "
            "    c.current_depth = $current_depth, "
            "    c.updated_at = datetime()",
            {
                "session_id": session_id,
                "papers_discovered": papers_discovered,
                "current_depth": current_depth,
            },
        )
