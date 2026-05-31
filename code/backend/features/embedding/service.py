"""Provider-agnostic paper and question embedding service for ALRS v2.

Extracted from ``services.graph_search_service.GraphSearchService`` —
the embed_papers, embed_papers_generator, and embed_questions methods
now live here, decoupled from the BFS orchestrator.

The service delegates actual vector generation to an
:class:`~features.embedding.providers.base.EmbeddingProvider`, making
it trivial to swap Gemini for OpenAI, a local model, etc.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from core.clients.rate_limiter import AdaptiveRateLimiter
    from core.db.neo4j_service import Neo4jService
    from features.embedding.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class PaperEmbeddingService:
    """Embeds papers and research questions using a pluggable provider.

    Attributes:
        _neo4j: Injected Neo4j graph database service.
        _provider: Embedding provider (Gemini, OpenAI, …).
        _rate_limiter: Optional rate limiter for API calls.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        provider: EmbeddingProvider,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._provider = provider
        self._rate_limiter = rate_limiter

    # ── Public API ───────────────────────────────────────────────────

    async def embed_paper(
        self,
        doi: str,
        *,
        session_id: str | None = None,
    ) -> bool:
        """Embed a single paper by DOI and store the vector in Neo4j.

        Skips papers that already have an embedding or lack an abstract.

        Args:
            doi: The paper DOI.
            session_id: Optional session identifier for telemetry.

        Returns:
            ``True`` if a new embedding was stored, ``False`` if skipped.
        """
        if await self._neo4j.has_embedding(doi):
            return False

        abstract = await self._neo4j.get_paper_abstract(doi)
        if not abstract:
            return False

        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

        embedding = await self._provider.embed_document(
            abstract, session_id=session_id,
        )
        await self._neo4j.store_paper_embedding(
            doi, embedding, model=self._provider.model_name,
        )
        return True

    async def embed_papers(
        self,
        dois: list[str],
        *,
        session_id: str | None = None,
    ) -> int:
        """Embed multiple papers sequentially.

        Args:
            dois: List of DOIs to embed.
            session_id: Optional session identifier for telemetry.

        Returns:
            Number of papers that were newly embedded.
        """
        embedded_count = 0
        for doi in dois:
            try:
                if await self.embed_paper(doi, session_id=session_id):
                    embedded_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to embed DOI %s: %s', doi, exc)
        return embedded_count

    async def embed_papers_stream(
        self,
        dois: list[str],
        *,
        session_id: str | None = None,
        base_pct: float = 0.0,
        max_pct: float = 100.0,
    ) -> AsyncIterator[dict[str, object]]:
        """Embed papers and yield progress dicts every 10 papers.

        Yields dicts with keys ``embedded``, ``total``, and ``progress_pct``
        for the caller to convert into progress events.

        Args:
            dois: List of DOIs to embed.
            session_id: Optional session identifier for telemetry.
            base_pct: Starting percentage for progress reporting.
            max_pct: Ending percentage for progress reporting.

        Yields:
            Progress dicts: ``{"embedded": int, "total": int, "progress_pct": float}``.
        """
        embedded_count = 0
        total = len(dois)

        for idx, doi in enumerate(dois):
            try:
                if await self.embed_paper(doi, session_id=session_id):
                    embedded_count += 1

                if (idx + 1) % 10 == 0:
                    pct = base_pct + (max_pct - base_pct) * ((idx + 1) / total)
                    yield {
                        "embedded": embedded_count,
                        "total": total,
                        "progress_pct": pct,
                    }
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to embed DOI %s: %s', doi, exc)

    async def embed_questions(
        self,
        session_id: str,
        questions: list[str],
    ) -> None:
        """Embed research questions and store them in Neo4j.

        Args:
            session_id: The session that owns these questions.
            questions: List of research question texts.
        """
        for question in questions:
            try:
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()

                embedding = await self._provider.embed_query(
                    question, session_id=session_id,
                )
                await self._neo4j.store_question_embedding(
                    session_id=session_id,
                    question_text=question,
                    embedding=embedding,
                    model=self._provider.model_name,
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

    async def has_embedding(self, doi: str) -> bool:
        """Check if a paper already has an embedding stored.

        Args:
            doi: The paper DOI.

        Returns:
            ``True`` if the paper has an embedding in Neo4j.
        """
        return await self._neo4j.has_embedding(doi)
