"""BFS citation crawl engine for ALRS v2.

Orchestrates breadth-first search across the scholarly citation graph:
  1. Fetches papers and their citations/references from OpenAlex
  2. Stores the citation graph in Neo4j
  3. Embeds paper abstracts via Gemini (vectors stay in Neo4j, never in RAM)
  4. Supports both automated (full crawl) and interactive (pause-per-level) modes
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

from models.paper import PaperCreate
from models.progress import CycleResultsData, EventType, ProgressEvent

if TYPE_CHECKING:
    from db.neo4j_service import Neo4jService
    from services.gemini_service import GeminiService
    from services.log_service import LogService
    from services.openalex_service import OpenAlexService
    from services.rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)

# Type alias for the progress callback accepted by public methods.
ProgressCallback = Callable[[ProgressEvent], Coroutine[Any, Any, None]] | None


class CycleResult(BaseModel):
    """Result of a single BFS level expansion."""

    level: int
    papers_discovered: int
    papers_new: int
    new_dois: list[str]
    errors: list[str] = Field(default_factory=list)


class GraphSearchService:
    """BFS citation crawl engine.

    Collaborators
    -------------
    - ``Neo4jService``  – graph persistence (papers, citations, embeddings)
    - ``OpenAlexService`` – scholarly metadata & citation lists
    - ``GeminiService``   – abstract → embedding vectors
    - ``AdaptiveRateLimiter`` – token-bucket rate control for external APIs
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        gemini: GeminiService,
        rate_limiter: AdaptiveRateLimiter | None = None,
        log_service: LogService | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex
        self._gemini = gemini
        self._rate_limiter = rate_limiter
        self._log_service = log_service

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    async def _emit(
        self,
        callback: ProgressCallback,
        event_type: EventType,
        session_id: str,
        progress_percent: float,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """Build and dispatch a ``ProgressEvent`` if a callback is set."""
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

    # ------------------------------------------------------------------
    # BFS cycle (single level)
    # ------------------------------------------------------------------

    async def run_bfs_cycle(
        self,
        session_id: str,
        queued_dois: list[str],
        current_depth: int,
        max_depth: int,
        progress_callback: ProgressCallback = None,
    ) -> CycleResult:
        """Execute one BFS level: fetch → store → expand citations.

        For every DOI in *queued_dois*:
          1. Skip if already present in Neo4j.
          2. Fetch metadata from OpenAlex.
          3. MERGE the paper node in Neo4j and link to the session.
          4. Fetch forward citations and backward references.
          5. For each neighbour DOI create a stub Paper node (if absent)
             and a ``CITES`` edge.
          6. Collect DOIs not yet seen in the session for the next level.

        Returns a :class:`CycleResult` summarising the level.
        """
        errors: list[str] = []
        new_dois_set: set[str] = set()
        papers_discovered = 0
        papers_new = 0
        total = len(queued_dois)

        # Pre-fetch all DOIs already in this session to avoid duplicate work.
        existing_session_dois: set[str] = set(
            await self._neo4j.get_session_dois(session_id)
        )

        for idx, doi in enumerate(queued_dois):
            try:
                # ---- progress -------------------------------------------
                pct = ((idx + 1) / total) * 100 if total else 0
                await self._emit(
                    progress_callback,
                    EventType.LEVEL_COMPLETE,
                    session_id,
                    pct,
                    f'Processing DOI {idx + 1}/{total}: {doi}',
                    {'doi': doi, 'level': current_depth},
                )

                # ---- 1. skip if already in the session graph ------------
                if doi in existing_session_dois:
                    logger.debug('Skipping already-processed DOI: %s', doi)
                    continue

                # ---- 2. fetch from OpenAlex -----------------------------
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                paper: PaperCreate | None = await self._openalex.get_paper_by_doi(
                    doi, session_id=session_id,
                )
                if paper is None:
                    logger.warning('Paper not found in OpenAlex: %s', doi)
                    errors.append(f'Not found in OpenAlex: {doi}')
                    continue

                # ---- 3. store in Neo4j ----------------------------------
                await self._neo4j.create_paper(paper)
                await self._neo4j.link_paper_to_session(
                    doi=paper.doi,
                    session_id=session_id,
                    depth=current_depth,
                )
                existing_session_dois.add(paper.doi)
                papers_discovered += 1
                papers_new += 1

                # ---- 4. fetch citations & references --------------------
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                citing_dois = await self._openalex.get_citations(
                    doi, session_id=session_id,
                )

                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                referenced_dois = await self._openalex.get_references(
                    doi, session_id=session_id,
                )

                # ---- 5. create edges & stub nodes -----------------------
                neighbour_dois: list[str] = []
                for cited_doi in citing_dois:
                    await self._ensure_stub_and_cite(
                        citing_doi=cited_doi,
                        cited_doi=doi,
                    )
                    neighbour_dois.append(cited_doi)

                for ref_doi in referenced_dois:
                    await self._ensure_stub_and_cite(
                        citing_doi=doi,
                        cited_doi=ref_doi,
                    )
                    neighbour_dois.append(ref_doi)

                # ---- 6. collect NEW DOIs for next level -----------------
                for ndoi in neighbour_dois:
                    if ndoi not in existing_session_dois:
                        new_dois_set.add(ndoi)

            except Exception as exc:  # noqa: BLE001
                msg = f'Error processing DOI {doi}: {exc}'
                logger.exception(msg)
                errors.append(msg)
                # Log but don't abort — keep crawling remaining DOIs.

        # Log to structured log service if available.
        if self._log_service is not None:
            await self._log_service.log(
                level='INFO',
                module='graph_search_service',
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

    # ------------------------------------------------------------------
    # Stub-node helper (keeps the graph well-formed)
    # ------------------------------------------------------------------

    async def _ensure_stub_and_cite(
        self,
        citing_doi: str,
        cited_doi: str,
    ) -> None:
        """Ensure both endpoint Paper nodes exist, then MERGE a CITES edge.

        If a paper node does not exist yet, a minimal stub is created with
        only the DOI so the relationship can be established. The stub will
        be enriched when (if) that DOI is processed in a future BFS level.
        """
        for doi in (citing_doi, cited_doi):
            if not await self._neo4j.paper_exists(doi):
                stub = PaperCreate(
                    doi=doi,
                    title='[pending]',
                    source='stub',
                )
                await self._neo4j.create_paper(stub)

        await self._neo4j.create_citation(citing_doi, cited_doi)

    # ------------------------------------------------------------------
    # Full search orchestration
    # ------------------------------------------------------------------

    async def run_full_search(
        self,
        session_id: str,
        seed_doi: str,
        research_questions: list[str],
        similarity_threshold: float,
        max_depth: int,
        mode: str,
        progress_callback: ProgressCallback = None,
    ) -> None:
        """Drive the complete BFS crawl from seed to final ranking.

        Modes
        -----
        ``automated``
            Runs all levels back-to-back, embedding after each level.
        ``interactive``
            Pauses after each level and emits ``CYCLE_RESULTS`` so the
            caller can selectively enqueue DOIs for the next level.

        Parameters
        ----------
        session_id:
            Unique session identifier.
        seed_doi:
            Starting DOI for the crawl.
        research_questions:
            List of research questions to embed for similarity ranking.
        similarity_threshold:
            Minimum cosine similarity for a paper to be considered relevant.
        max_depth:
            Maximum BFS depth (0-indexed levels).
        mode:
            ``"automated"`` or ``"interactive"``.
        progress_callback:
            Optional async callable that receives ``ProgressEvent`` updates.
        """
        # ---- 0. SEARCH_STARTED ------------------------------------------
        await self._emit(
            progress_callback,
            EventType.SEARCH_STARTED,
            session_id,
            0.0,
            f'Starting BFS search from seed DOI: {seed_doi}',
            {'seed_doi': seed_doi, 'max_depth': max_depth, 'mode': mode},
        )

        # Embed the research questions up-front.
        await self.embed_questions(session_id, research_questions)

        queue: list[str] = [seed_doi]

        for depth in range(max_depth + 1):
            if not queue:
                logger.info(
                    'No DOIs queued at depth %d — stopping early', depth,
                )
                break

            # -- progress bookkeeping ------------------------------------
            level_pct_base = (depth / (max_depth + 1)) * 100

            await self._emit(
                progress_callback,
                EventType.LEVEL_COMPLETE,
                session_id,
                level_pct_base,
                f'Starting BFS level {depth} ({len(queue)} DOIs)',
                {'level': depth, 'queue_size': len(queue)},
            )

            # -- a. run BFS cycle ----------------------------------------
            cycle = await self.run_bfs_cycle(
                session_id=session_id,
                queued_dois=queue,
                current_depth=depth,
                max_depth=max_depth,
                progress_callback=progress_callback,
            )

            # -- b. emit LEVEL_COMPLETE ----------------------------------
            await self._emit(
                progress_callback,
                EventType.LEVEL_COMPLETE,
                session_id,
                level_pct_base + 5,
                (
                    f'Level {depth} done: {cycle.papers_new} new papers, '
                    f'{len(cycle.new_dois)} candidate DOIs'
                ),
                {
                    'level': depth,
                    'papers_discovered': cycle.papers_discovered,
                    'papers_new': cycle.papers_new,
                    'new_dois_count': len(cycle.new_dois),
                },
            )

            # -- c. embed newly discovered papers (skip those w/o abstracts)
            unembedded_dois = await self._neo4j.get_unembedded_dois(session_id)
            if unembedded_dois:
                embedded_count = await self.embed_papers(
                    unembedded_dois, progress_callback,
                )
                await self._emit(
                    progress_callback,
                    EventType.EMBEDDING_PROGRESS,
                    session_id,
                    level_pct_base + 10,
                    f'Embedded {embedded_count} papers at level {depth}',
                    {'embedded_count': embedded_count, 'level': depth},
                )

            # -- d. decide next queue ------------------------------------
            if mode == 'interactive':
                # Emit results and STOP — caller must enqueue DOIs.
                cycle_data = CycleResultsData(
                    level=depth,
                    papers_discovered=cycle.papers_discovered,
                    papers_new=cycle.papers_new,
                )
                await self._emit(
                    progress_callback,
                    EventType.CYCLE_RESULTS,
                    session_id,
                    level_pct_base + 15,
                    f'Level {depth} results ready — awaiting enqueue',
                    cycle_data.model_dump(),  # type: ignore[arg-type]
                )
                logger.info(
                    'Interactive mode: pausing after level %d for session %s',
                    depth,
                    session_id,
                )
                return  # Control returns to the caller / router.

            # Automated: feed ALL new DOIs into the next level.
            queue = cycle.new_dois

        # ---- final: update stats & emit SEARCH_COMPLETE -----------------
        stats = await self._neo4j.update_session_stats(session_id)
        await self._emit(
            progress_callback,
            EventType.SEARCH_COMPLETE,
            session_id,
            100.0,
            'BFS search complete',
            {
                'total_papers': stats.get('total_papers', 0),
                'embedded_papers': stats.get('embedded_papers', 0),
            },
        )

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    async def embed_papers(
        self,
        dois: list[str],
        progress_callback: ProgressCallback = None,
    ) -> int:
        """Embed papers that are missing embeddings.

        For each DOI:
          1. Check ``has_embedding`` in Neo4j — skip if already done.
          2. Fetch the abstract from Neo4j (not Python memory for vectors).
          3. Call ``GeminiService.embed_paper`` to obtain the vector.
          4. Store the vector back on the Paper node in Neo4j.

        Returns the count of newly embedded papers.
        """
        embedded_count = 0
        total = len(dois)

        for idx, doi in enumerate(dois):
            try:
                # Already embedded?
                if await self._neo4j.has_embedding(doi):
                    continue

                # Fetch abstract from graph.
                abstract = await self._neo4j.get_paper_abstract(doi)
                if not abstract:
                    logger.debug('No abstract for DOI %s — skipping embedding', doi)
                    continue

                # Rate-limit Gemini calls.
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._gemini.embed_paper(abstract)

                # Store directly in Neo4j — never hold in Python beyond this scope.
                await self._neo4j.store_paper_embedding(doi, embedding)
                embedded_count += 1

                # Periodic progress feedback.
                if progress_callback is not None and (idx + 1) % 10 == 0:
                    pct = ((idx + 1) / total) * 100 if total else 0
                    await self._emit(
                        progress_callback,
                        EventType.EMBEDDING_PROGRESS,
                        '',  # session_id not available here
                        pct,
                        f'Embedded {embedded_count}/{total} papers',
                        {'embedded': embedded_count, 'total': total},
                    )

            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to embed DOI %s: %s', doi, exc)
                # Continue with remaining DOIs.

        return embedded_count

    async def embed_questions(
        self,
        session_id: str,
        questions: list[str],
    ) -> None:
        """Embed research questions and store them in Neo4j.

        Each question is embedded using ``RETRIEVAL_QUERY`` task type
        and persisted on a ``Question`` node keyed by (session_id, text).
        """
        for question in questions:
            try:
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._gemini.embed_question(question)
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
