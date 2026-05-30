"""Gemini embedding service for paper and question embeddings."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

if TYPE_CHECKING:
    from services.log_service import LogService

logger = logging.getLogger(__name__)


class GeminiService:
    """Client for the Gemini embedding API.

    Uses gemini-embedding-001 with task_type parameter for optimized
    retrieval embeddings. Supports configurable output dimensions via MRL.
    """

    MODEL_NAME = "gemini-embedding-001"

    def __init__(
        self,
        api_key: str,
        output_dimensionality: int = 768,
        log_service: LogService | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._output_dimensionality = output_dimensionality
        self._log_service = log_service

    async def embed_paper(self, text: str) -> list[float]:
        """Embed a paper's abstract using RETRIEVAL_DOCUMENT task type.

        Args:
            text: Paper abstract or concatenated title + abstract.

        Returns:
            Embedding vector as list of floats.
        """
        return await self._embed(text, task_type="RETRIEVAL_DOCUMENT")

    async def embed_question(self, question: str) -> list[float]:
        """Embed a research question using RETRIEVAL_QUERY task type.

        Args:
            question: The research question text.

        Returns:
            Embedding vector as list of floats.
        """
        return await self._embed(question, task_type="RETRIEVAL_QUERY")

    async def _embed(self, text: str, task_type: str) -> list[float]:
        """Internal embedding method with logging.

        Args:
            text: Text to embed.
            task_type: Gemini embedding task type.

        Returns:
            Normalized embedding vector.
        """
        import time

        start_ms = int(time.monotonic() * 1000)

        result = self._client.models.embed_content(
            model=self.MODEL_NAME,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self._output_dimensionality,
            ),
        )

        elapsed_ms = int(time.monotonic() * 1000) - start_ms

        if self._log_service is not None:
            await self._log_service.log_api_request(
                service="gemini",
                method="POST",
                url=f"models/{self.MODEL_NAME}:embedContent",
                status_code=200,
                response_time_ms=elapsed_ms,
                payload_summary=f"task_type={task_type}, dims={self._output_dimensionality}, "
                f"text_len={len(text)}",
            )

        # Extract embedding values — gemini-embedding-001 returns individual
        # embeddings for each content item
        embedding = result.embeddings[0]
        values: list[float] = list(embedding.values)

        # Manual normalization required for gemini-embedding-001 when using
        # non-3072 dimensions (per Gemini Embeddings Reference)
        if self._output_dimensionality != 3072:
            values = self._normalize(values)

        logger.debug(
            "Embedded text (%d chars) -> %d dims in %dms",
            len(text),
            len(values),
            elapsed_ms,
        )
        return values

    @staticmethod
    def _normalize(embedding: list[float]) -> list[float]:
        """L2-normalize an embedding vector.

        Required for gemini-embedding-001 when output_dimensionality != 3072.
        """
        import math

        norm = math.sqrt(sum(x * x for x in embedding))
        if norm == 0.0:
            return embedding
        return [x / norm for x in embedding]
