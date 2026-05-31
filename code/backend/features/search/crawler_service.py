"""BFS crawler service for extracting OpenAlex data into Neo4j."""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

from features.retrieval.models import PaperCreate
from features.search.models import EventType, ProgressEvent

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.logging.log_service import LogService
    from core.clients.openalex_client import OpenAlexService
    from core.clients.rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent], Coroutine[Any, Any, None]] | None


class CycleResult(BaseModel):
    """Result of a single BFS level expansion."""

    level: int
    papers_discovered: int
    papers_new: int
    new_dois: list[str]
    errors: list[str] = Field(default_factory=list)


class CrawlerService:
    """BFS citation crawl engine that populates Neo4j from OpenAlex."""

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        rate_limiter: AdaptiveRateLimiter | None = None,
        log_service: LogService | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex
        self._rate_limiter = rate_limiter
        self._log_service = log_service

    async def _emit(
        self,
        callback: ProgressCallback,
        event_type: EventType,
        session_id: str,
        progress_percent: float,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        if callback is None:
            return
        event = ProgressEvent(
            event_type=event_type,
            session_id=session_id,
            progress_percent=min(progress_percent, 100.0),
            message=message,
            data=data,
        )
        await callback(event)

    async def run_bfs_cycle(
        self,
        session_id: str,
        queued_dois: list[str],
        current_depth: int,
        max_depth: int,
        progress_callback: ProgressCallback = None,
    ) -> CycleResult:
        import asyncio

        errors: list[str] = []
        new_dois_set: set[str] = set()
        papers_discovered = 0
        papers_new = 0

        existing_session_dois: set[str] = set(
            await self._neo4j.get_session_dois(session_id)
        )

        dois_to_process = [
            d for d in queued_dois
            if d not in existing_session_dois or current_depth == 1
        ]
        total = len(dois_to_process)

        if not dois_to_process:
            return CycleResult(
                level=current_depth,
                papers_discovered=0,
                papers_new=0,
                new_dois=[],
            )

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id,
            10.0,
            f'Batch fetching {total} papers for level {current_depth}...',
        )

        try:
            papers = await self._openalex.batch_get_papers_by_dois(
                dois_to_process, session_id=session_id
            )
        except Exception as e:
            msg = f"Error fetching batch papers: {e}"
            logger.exception(msg)
            errors.append(msg)
            papers = []
        fetched_papers_map = {p.doi: p for p in papers}

        for doi in dois_to_process:
            paper = fetched_papers_map.get(doi)
            if not paper:
                logger.warning('Paper not found in OpenAlex: %s', doi)
                errors.append(f'Not found in OpenAlex: {doi}')
                continue
            
            await self._neo4j.create_paper(paper)
            await self._neo4j.link_paper_to_session(
                doi=paper.doi,
                session_id=session_id,
                depth=current_depth,
            )
            existing_session_dois.add(paper.doi)
            papers_discovered += 1
            papers_new += 1

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id,
            50.0,
            f'Fetching citations/references concurrently for {papers_new} papers...',
        )

        async def _fetch_edges(p: PaperCreate) -> tuple[str, list[str], list[str]]:
            try:
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                citing = await self._openalex.get_citations(
                    p.doi, session_id=session_id, openalex_id=p.openalex_id
                )
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                refs = await self._openalex.get_references(
                    p.doi, session_id=session_id, openalex_id=p.openalex_id
                )
                return p.doi, citing, refs
            except Exception as e:
                msg = f'Error fetching edges for {p.doi}: {e}'
                logger.exception(msg)
                errors.append(msg)
                return p.doi, [], []

        tasks = [_fetch_edges(p) for p in papers]
        edge_results = await asyncio.gather(*tasks)

        for doi, citing_dois, referenced_dois in edge_results:
            neighbour_dois: list[str] = []
            
            for cited_doi in citing_dois:
                await self._neo4j.ensure_stub_and_cite(
                    citing_doi=cited_doi,
                    cited_doi=doi,
                )
                neighbour_dois.append(cited_doi)

            for ref_doi in referenced_dois:
                await self._neo4j.ensure_stub_and_cite(
                    citing_doi=doi,
                    cited_doi=ref_doi,
                )
                neighbour_dois.append(ref_doi)

            for ndoi in neighbour_dois:
                if ndoi not in existing_session_dois:
                    new_dois_set.add(ndoi)

        if self._log_service is not None:
            await self._log_service.log(
                level='INFO',
                module='crawler_service',
                message=(
                    f'BFS level {current_depth} complete: '
                    f'{papers_new} new papers, {len(new_dois_set)} new DOIs'
                ),
                session_id=session_id,
                extra={
                    'level': current_depth,
                    'papers_new': papers_new,
                    'new_dois_count': len(new_dois_set),
                    'errors_count': len(errors),
                },
            )

        return CycleResult(
            level=current_depth,
            papers_discovered=papers_discovered,
            papers_new=papers_new,
            new_dois=sorted(new_dois_set),
            errors=errors,
        )


