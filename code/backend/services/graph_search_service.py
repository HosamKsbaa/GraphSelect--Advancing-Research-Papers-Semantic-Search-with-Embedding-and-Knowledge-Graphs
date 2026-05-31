"""BFS citation crawl engine for ALRS v2.

Orchestrates breadth-first search across the scholarly citation graph using
CrawlerService, RankingService, and GeminiService.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING, AsyncIterator

from models.progress import CycleResultsData, EventType, ProgressEvent

if TYPE_CHECKING:
    from db.neo4j_service import Neo4jService
    from models.ranked_paper import GroupedResults
    from services.gemini_service import GeminiService
    from services.log_service import LogService
    from services.openalex_service import OpenAlexService
    from services.rate_limiter import AdaptiveRateLimiter
    from services.crawler_service import CrawlerService
    from services.ranking_service import RankingService

logger = logging.getLogger(__name__)


class GraphSearchService:
    """Facade orchestrating BFS crawling, embedding, and ranking."""

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        gemini: GeminiService,
        crawler: CrawlerService,
        ranking: RankingService,
        rate_limiter: AdaptiveRateLimiter | None = None,
        log_service: LogService | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._gemini = gemini
        self._rate_limiter = rate_limiter
        self._log_service = log_service
        self._crawler = crawler
        self._ranking = ranking

    async def run_full_search(
        self,
        session_id: str,
        seed_doi: str,
        research_questions: list[str],
        similarity_threshold: float,
        max_depth: int,
        mode: str,
        queued_dois: list[str] | None = None,
    ) -> AsyncIterator[ProgressEvent]:
        """Drive the complete BFS crawl from seed to final ranking."""
        yield ProgressEvent(
            event_type=EventType.SEARCH_STARTED,
            session_id=session_id,
            progress_percent=0.0,
            message=f'Starting BFS search from seed DOI: {seed_doi}',
            data={'seed_doi': seed_doi, 'max_depth': max_depth, 'mode': mode},
        )

        queue: list[str] = queued_dois if queued_dois is not None else [seed_doi]

        # For automated mode, depth goes from 0 to max_depth
        # In interactive mode, this might be called for a specific level, but let's assume it handles the remaining depth.
        # Wait, if queued_dois is provided, we might be resuming. Let's just run max_depth cycles.
        total_discovered = 0

        for depth in range(max_depth):
            if not queue:
                logger.info('No DOIs queued at depth %d — stopping early', depth)
                break

            progress_base = (depth / max_depth) * 80

            yield ProgressEvent(
                event_type=EventType.LEVEL_COMPLETE,
                session_id=session_id,
                progress_percent=progress_base,
                message=f'Starting BFS level {depth} ({len(queue)} DOIs)',
                data={'level': depth, 'queue_size': len(queue)},
            )

            import asyncio
            q: asyncio.Queue[ProgressEvent] = asyncio.Queue()

            async def progress_callback(evt: ProgressEvent) -> None:
                await q.put(evt)

            task = asyncio.create_task(
                self._crawler.run_bfs_cycle(
                    session_id=session_id,
                    queued_dois=queue,
                    current_depth=depth + 1,
                    max_depth=max_depth,
                    progress_callback=progress_callback,
                )
            )

            while not task.done():
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=0.1)
                    yield evt
                except asyncio.TimeoutError:
                    pass

            while not q.empty():
                yield q.get_nowait()

            cycle = task.result()

            total_discovered += cycle.papers_discovered

            yield ProgressEvent(
                event_type=EventType.LEVEL_COMPLETE,
                session_id=session_id,
                progress_percent=progress_base + (40 / max_depth),
                message=(
                    f'Level {depth + 1} done: {cycle.papers_new} new papers, '
                    f'{len(cycle.new_dois)} candidate DOIs'
                ),
                data={
                    'level': depth + 1,
                    'papers_discovered': cycle.papers_discovered,
                    'papers_new': cycle.papers_new,
                    'new_dois_count': len(cycle.new_dois),
                },
            )

            unembedded_dois = await self._neo4j.get_unembedded_dois(session_id)
            if unembedded_dois:
                yield ProgressEvent(
                    event_type=EventType.EMBEDDING_PROGRESS,
                    session_id=session_id,
                    progress_percent=progress_base + (60 / max_depth),
                    message=f'Embedding {cycle.papers_new} new papers...',
                )

                async for evt in self.embed_papers_generator(
                    unembedded_dois, session_id=session_id, base_pct=progress_base + (60 / max_depth), max_pct=progress_base + (70 / max_depth)
                ):
                    yield evt

                yield ProgressEvent(
                    event_type=EventType.EMBEDDING_PROGRESS,
                    session_id=session_id,
                    progress_percent=progress_base + (70 / max_depth),
                    message=f'Embedded {len(unembedded_dois)} papers',
                    data={'embedded_count': len(unembedded_dois)},
                )

            if mode == 'interactive':
                cycle_data = CycleResultsData(
                    level=depth + 1,
                    papers_discovered=cycle.papers_discovered,
                    papers_new=cycle.papers_new,
                )
                yield ProgressEvent(
                    event_type=EventType.CYCLE_RESULTS,
                    session_id=session_id,
                    progress_percent=progress_base + (80 / max_depth),
                    message=f'Level {depth + 1} results ready — awaiting enqueue',
                    data=cycle_data.model_dump(), # type: ignore
                )
                logger.info('Interactive mode: pausing after level %d for session %s', depth + 1, session_id)
                return

            queue = cycle.new_dois

        await self.embed_questions(session_id, research_questions)

        yield ProgressEvent(
            event_type=EventType.EMBEDDING_PROGRESS,
            session_id=session_id,
            progress_percent=85.0,
            message="Research questions embedded",
        )

        stats = await self._neo4j.update_session_stats(session_id)
        yield ProgressEvent(
            event_type=EventType.SEARCH_COMPLETE,
            session_id=session_id,
            progress_percent=100.0,
            message=f'Search complete! {total_discovered} papers discovered.',
            data={
                'total_papers': stats.get('total_papers', 0),
                'embedded_papers': stats.get('embedded_papers', 0),
            },
        )

    async def embed_papers(
        self,
        dois: list[str],
        session_id: str | None = None,
    ) -> int:
        embedded_count = 0
        for idx, doi in enumerate(dois):
            try:
                if await self._neo4j.has_embedding(doi):
                    continue

                abstract = await self._neo4j.get_paper_abstract(doi)
                if not abstract:
                    continue

                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._gemini.embed_paper(abstract, session_id=session_id)

                await self._neo4j.store_paper_embedding(doi, embedding)
                embedded_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to embed DOI %s: %s', doi, exc)
        return embedded_count

    async def embed_papers_generator(
        self,
        dois: list[str],
        session_id: str | None = None,
        base_pct: float = 0.0,
        max_pct: float = 100.0,
    ) -> AsyncIterator[ProgressEvent]:
        embedded_count = 0
        total = len(dois)

        for idx, doi in enumerate(dois):
            try:
                if await self._neo4j.has_embedding(doi):
                    continue

                abstract = await self._neo4j.get_paper_abstract(doi)
                if not abstract:
                    continue

                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._gemini.embed_paper(abstract, session_id=session_id)

                await self._neo4j.store_paper_embedding(doi, embedding)
                embedded_count += 1

                if (idx + 1) % 10 == 0:
                    pct = base_pct + (max_pct - base_pct) * ((idx + 1) / total)
                    yield ProgressEvent(
                        event_type=EventType.EMBEDDING_PROGRESS,
                        session_id=session_id or '',
                        progress_percent=pct,
                        message=f'Embedded {embedded_count}/{total} papers',
                        data={'embedded': embedded_count, 'total': total},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to embed DOI %s: %s', doi, exc)

    async def embed_questions(
        self,
        session_id: str,
        questions: list[str],
    ) -> None:
        for question in questions:
            try:
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._gemini.embed_question(question, session_id=session_id)
                await self._neo4j.store_question_embedding(
                    session_id=session_id,
                    question_text=question,
                    embedding=embedding,
                )
                logger.info(
                    'Embedded question for session %s: %.60s…',
                    session_id,
                    question,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    'Failed to embed question "%s": %s', question, exc,
                )

    async def rank_papers(
        self,
        session_id: str,
        similarity_weight: float = 0.7,
        pagerank_weight: float = 0.3,
    ) -> GroupedResults:
        return await self._ranking.rank_papers(
            session_id=session_id,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
        )
