"""Search session lifecycle service for ALRS v2.

Encapsulates all business logic for creating, configuring, and streaming
literature review search sessions. This keeps the search router thin —
it only validates HTTP input and delegates to this service.

Architecture:
    Router (HTTP) → SearchSessionService (orchestration) → DB / API workers

Responsibilities:
    - create_session(): Validates the seed DOI via OpenAlex, persists the
      session row in MySQL, and MERGEs the seed paper node in Neo4j.
    - enqueue_papers(): Stores the researcher's DOI selections for the
      next BFS cycle in the session's JSON state column.
    - build_search_stream(): Constructs the full service dependency graph
      and returns an async generator of SSE ProgressEvents.
"""
from __future__ import annotations

import json
import logging
import uuid
import asyncio
from typing import AsyncIterator, Any

from features.retrieval.models import PaperSummary
from features.sessions.models import (
    SearchMode,
    SearchRequest,
    SearchResponse,
    SessionStatus,
)
from features.search.models import EventType, ProgressEvent

from core.db.neo4j_service import Neo4jService
from core.db.mysql_service import MySQLService
from core.clients.openalex_client import OpenAlexService

logger = logging.getLogger(__name__)


class SearchSessionService:
    """Manages the lifecycle of a search session (create → enqueue → stream).

    This service owns all the business logic that was previously inlined
    in the search router endpoints. Each public method maps 1-to-1 with
    a router endpoint.

    Attributes:
        _neo4j: Neo4j graph database service for paper/session nodes.
        _mysql: MySQL relational database service for session metadata.
        _openalex: OpenAlex API client for paper metadata retrieval.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        mysql: MySQLService,
        openalex: OpenAlexService,
    ) -> None:
        self._neo4j = neo4j
        self._mysql = mysql
        self._openalex = openalex

    # ------------------------------------------------------------------
    # Session creation
    # ------------------------------------------------------------------

    async def create_session(self, request: SearchRequest) -> SearchResponse:
        """Create a new search session from a validated SearchRequest.

        Steps:
            1. Generate a UUID session ID.
            2. INSERT the session row into MySQL with status=CREATED.
            3. Fetch the seed paper metadata from OpenAlex.
            4. MERGE the seed Paper node into Neo4j and link it to the
               Session node at depth 0.

        Args:
            request: Validated search request containing seed_doi,
                     research_questions, thresholds, and mode.

        Returns:
            SearchResponse with the new session_id and confirmation.

        Raises:
            ValueError: If seed_doi is None.
            LookupError: If the DOI is not found in OpenAlex.
            RuntimeError: If OpenAlex call fails unexpectedly.
        """
        seed_doi = request.seed_doi
        if seed_doi is None:
            raise ValueError(
                "seed_doi is required. Use /resolve-title to search by title first."
            )

        # Step 1: Generate session ID
        session_id = str(uuid.uuid4())

        # Step 2: Persist session row in MySQL
        await self._mysql.execute(
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

        # Step 3: Fetch seed paper from OpenAlex
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

        # Step 4: MERGE seed paper into Neo4j graph
        await self._neo4j.execute_write(
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

        # Link Session → Paper at depth 0
        await self._neo4j.execute_write(
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

    # ------------------------------------------------------------------
    # Paper enqueue (interactive mode)
    # ------------------------------------------------------------------

    async def enqueue_papers(
        self, session_id: str, dois: list[str]
    ) -> dict[str, object]:
        """Store researcher-selected DOIs for the next BFS cycle.

        Updates the session's ``full_state`` JSON column with an
        ``enqueued_dois`` array and flips status back to ``running``.

        Args:
            session_id: Target session UUID.
            dois: List of DOIs the researcher selected.

        Returns:
            Confirmation dict with count and DOI list.

        Raises:
            LookupError: If the session does not exist.
        """
        session = await self._mysql.get_session(session_id)
        if session is None:
            raise LookupError(f"Session not found: {session_id}")

        await self._mysql.execute(
            """UPDATE sessions
               SET full_state = JSON_SET(
                       COALESCE(full_state, '{}'), '$.enqueued_dois', %s
                   ),
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

    # ------------------------------------------------------------------
    # SSE stream factory
    # ------------------------------------------------------------------

    async def build_search_stream(
        self,
        session_id: str,
        session_data: dict[str, Any],
        neo4j_service: Neo4jService,
        mysql_service: MySQLService,
    ) -> AsyncIterator[dict[str, str]]:
        """Build and return an async SSE event generator for a BFS search.

        This method constructs the full service dependency graph
        (OpenAlex → Gemini → Crawler → Ranking → GraphSearchService)
        and yields SSE-formatted dicts as the BFS progresses.

        Args:
            session_id: The session to stream.
            session_data: Raw session row from MySQL.
            neo4j_service: Live Neo4j connection from app state.
            mysql_service: Live MySQL connection from app state.

        Yields:
            Dicts with ``event`` and ``data`` keys suitable for
            ``EventSourceResponse``.
        """
        # Lazy imports to avoid circular dependencies at module level
        from features.embedding.providers.gemini_provider import GeminiService
        from core.clients.rate_limiter import AdaptiveRateLimiter
        from features.search.graph_search_service import GraphSearchService
        from features.search.crawler_service import CrawlerService
        from features.ranking.service import RankingService
        from core.logging.log_service import LogService
        from config import get_settings

        settings = get_settings()

        # --- Build the service dependency graph ---
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

        # --- Parse session parameters ---
        seed_doi: str = session_data["seed_doi"]
        research_questions: list[str] = (
            json.loads(session_data["research_questions"])
            if isinstance(session_data["research_questions"], str)
            else session_data["research_questions"]
        )
        similarity_threshold: float = float(session_data["similarity_threshold"])
        max_depth: int = int(session_data["max_depth"])
        mode: str = session_data["mode"]

        raw_state = session_data.get("full_state", "{}")
        full_state = json.loads(raw_state) if raw_state else {}
        queued_dois = full_state.get("enqueued_dois", [seed_doi])

        # --- Run the BFS search and stream events ---
        await mysql_service.update_session_status(
            session_id, SessionStatus.RUNNING.value
        )

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

                # Persist progress milestones to MySQL
                if (
                    evt.event_type == EventType.LEVEL_COMPLETE
                    and evt.data
                    and "papers_discovered" in evt.data
                ):
                    await mysql_service.update_session_progress(
                        session_id,
                        papers_discovered=evt.data.get("papers_discovered", 0),
                        current_depth=evt.data.get("level", 0),
                    )

            # Set final status based on mode
            if mode == SearchMode.AUTOMATED.value:
                await mysql_service.update_session_status(
                    session_id, SessionStatus.COMPLETED.value
                )
            else:
                await mysql_service.update_session_status(
                    session_id, SessionStatus.PAUSED.value
                )

        except asyncio.CancelledError:
            logger.info("Search stream cancelled for session %s", session_id)
            await mysql_service.update_session_status(
                session_id, SessionStatus.PAUSED.value
            )
            raise

        except Exception as exc:
            logger.exception("Search failed for session %s", session_id)
            await mysql_service.update_session_status(
                session_id, SessionStatus.FAILED.value
            )
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _mark_failed(self, session_id: str) -> None:
        """Set session status to FAILED in MySQL."""
        await self._mysql.execute(
            "UPDATE sessions SET status = %s WHERE session_id = %s",
            (SessionStatus.FAILED.value, session_id),
        )
