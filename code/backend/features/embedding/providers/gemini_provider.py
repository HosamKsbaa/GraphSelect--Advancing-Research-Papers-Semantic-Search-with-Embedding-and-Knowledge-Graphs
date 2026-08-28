"""Gemini embedding provider for ALRS v2.

Implements :class:`~features.embedding.providers.base.EmbeddingProvider`
using ``gemini-embedding-2`` — the multimodal embedding model from the
Gemini API.

This model does NOT support the ``task_type`` parameter; instead, task
instructions are included directly in the prompt text using the asymmetric
retrieval format:

  - Documents: ``"title: {title} | text: {content}"``
  - Queries:   ``"task: question answering | query: {content}"``

``gemini-embedding-2`` automatically renormalizes truncated/flexible
dimensions, so no manual normalization is needed (unlike
``gemini-embedding-001``).
"""
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from features.embedding.providers.base import EmbeddingProvider

if TYPE_CHECKING:
    from core.logging.log_service import LogService

logger = logging.getLogger(__name__)

_PLACEHOLDERS = {"", "your_gemini_api_key_here", "your_project_id_here", "your-gcp-project-id", "Not set", "None", "null"}


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by the Gemini API.

    Uses ``gemini-embedding-2`` with prompt-based task formatting for
    optimized retrieval embeddings.  Supports configurable output
    dimensions via MRL (Matryoshka Representation Learning).
    ``gemini-embedding-2`` automatically normalizes truncated dimensions.
    """

    def __init__(
        self,
        api_key: str | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        output_dimensionality: int = 768,
        log_service: LogService | None = None,
        model_name: str = "gemini-embedding-2",
    ) -> None:
        from config import get_settings
        settings = get_settings()

        self._use_vertex_ai: bool = vertexai if vertexai is not None else settings.use_vertex_ai
        self._output_dimensionality = output_dimensionality
        self._log_service = log_service
        self._model_name = model_name
        self._client: genai.Client | None = None

        if self._use_vertex_ai:
            self._mode = "vertex"
            self._project = (
                project or (settings.vertex_project if settings.vertex_project and settings.vertex_project not in _PLACEHOLDERS else None) or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
            ).strip()
            self._location = (
                location or settings.vertex_location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
            ).strip()
            self._api_key = None

            if self._project and self._project not in _PLACEHOLDERS:
                try:
                    self._client = genai.Client(
                        vertexai=True,
                        project=self._project,
                        location=self._location,
                    )
                    logger.info(
                        "GeminiEmbeddingProvider initialized via Vertex AI (project=%s, location=%s)",
                        self._project, self._location,
                    )
                except Exception as exc:
                    self._client = None
                    logger.warning("GeminiEmbeddingProvider failed to initialize Vertex client: %s", exc)
            else:
                self._client = None
                logger.warning("GeminiEmbeddingProvider: Vertex AI mode active but project is not set")
        else:
            self._mode = "studio"
            self._project = None
            self._location = None
            effective_key = (
                api_key
                or (settings.gemini_api_key if settings.gemini_api_key and settings.gemini_api_key not in _PLACEHOLDERS else None)
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or ""
            ).strip()
            if effective_key in _PLACEHOLDERS:
                effective_key = ""

            self._api_key = effective_key or None


            if self._api_key:
                try:
                    self._client = genai.Client(api_key=self._api_key, vertexai=False)
                    logger.info("GeminiEmbeddingProvider initialized via Google AI Studio")
                except Exception as exc:
                    self._client = None
                    logger.warning("GeminiEmbeddingProvider failed to initialize Studio client: %s", exc)
            else:
                self._client = None
                logger.warning("GeminiEmbeddingProvider initialized without credentials (GEMINI_API_KEY not configured)")


    # ── EmbeddingProvider interface ──────────────────────────────────

    @property
    def model_name(self) -> str:
        """Return the canonical model identifier."""
        return self._model_name

    @property
    def dimensions(self) -> int:
        """Return the configured output dimensionality."""
        return self._output_dimensionality

    async def embed_document(
        self,
        text: str,
        title: str | None = None,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a paper's abstract as a retrieval document.

        Args:
            text: Paper abstract or concatenated title + abstract.
            title: Optional paper title for the document format.
            session_id: Optional session identifier for telemetry.

        Returns:
            Embedding vector as list of floats.
        """
        formatted = self._format_document(text, title)
        return await self._embed(formatted, purpose="document", session_id=session_id)

    async def embed_paper(
        self,
        text: str,
        title: str | None = None,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Convenience alias for embed_document."""
        return await self.embed_document(text, title=title, session_id=session_id)

    async def embed_query(
        self,
        query: str,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a research question as a retrieval query.

        Args:
            query: The research question text.
            session_id: Optional session identifier for telemetry.

        Returns:
            Embedding vector as list of floats.
        """
        formatted = self._format_query(query, task="question answering")
        return await self._embed(formatted, purpose="query", session_id=session_id)

    # ── Prompt formatting (per Gemini Embeddings Reference) ──────────

    @staticmethod
    def _format_document(text: str, title: str | None = None) -> str:
        """Format text as a document for retrieval embedding.

        Uses the asymmetric format: ``"title: {title} | text: {content}"``
        If no title is provided, uses ``"title: none"``.
        """
        doc_title = title if title else "none"
        return f"title: {doc_title} | text: {text}"

    @staticmethod
    def _format_query(query: str, task: str = "question answering") -> str:
        """Format text as a query for retrieval embedding.

        Uses the asymmetric format: ``"task: {task} | query: {content}"``
        Supported tasks: search result, question answering, fact checking,
        code retrieval.
        """
        return f"task: {task} | query: {query}"

    # ── Internal ─────────────────────────────────────────────────────

    async def _embed(
        self,
        text: str,
        purpose: str = "document",
        session_id: str | None = None,
    ) -> list[float]:
        """Internal embedding method with retry logic and logging."""
        if self._client is None:
            logger.warning("Gemini API credentials not configured; using deterministic fallback embedding.")
            import hashlib
            import math
            h = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [(b / 255.0) * 2 - 1 for b in h]
            repeated = (raw * (self._output_dimensionality // len(raw) + 1))[:self._output_dimensionality]
            norm = math.sqrt(sum(x * x for x in repeated)) or 1.0
            return [x / norm for x in repeated]

        import asyncio
        import time
        from functools import partial

        loop = asyncio.get_running_loop()
        max_retries = 3

        for attempt in range(max_retries + 1):
            start_ms = int(time.monotonic() * 1000)
            try:
                func = partial(
                    self._client.models.embed_content,
                    model=self._model_name,
                    contents=text,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._output_dimensionality,
                    ),
                )
                result = await loop.run_in_executor(None, func)
                elapsed_ms = int(time.monotonic() * 1000) - start_ms

                if self._log_service is not None:
                    import json
                    req_body = json.dumps({
                        "model": self._model_name,
                        "contents": text,
                        "output_dimensionality": self._output_dimensionality
                    })

                    # Convert embeddings to dict for logging
                    resp_dict: dict[str, list[object]] = {"embeddings": []}
                    if hasattr(result, "embeddings"):
                        for emb in result.embeddings:
                            if hasattr(emb, "values"):
                                resp_dict["embeddings"].append(emb.values)
                            else:
                                resp_dict["embeddings"].append(emb)

                    resp_body = json.dumps(resp_dict)
                    if len(resp_body) > 50000:
                        resp_body = resp_body[:50000] + "...[TRUNCATED]"

                    await self._log_service.log_api_request(
                        service="Gemini",
                        method="POST",
                        url=f"models/{self._model_name}:embedContent",
                        status_code=200,
                        response_time_ms=elapsed_ms,
                        payload_summary=f"purpose={purpose}, dims={self._output_dimensionality}, "
                        f"text_len={len(text)}",
                        request_body=req_body,
                        response_body=resp_body,
                        session_id=session_id,
                    )
                break
            except Exception as exc:
                elapsed_ms = int(time.monotonic() * 1000) - start_ms
                status_code = getattr(exc, "code", getattr(exc, "status_code", 500))
                if status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

                if self._log_service is not None:
                    import json
                    req_body = json.dumps({
                        "model": self._model_name,
                        "contents": text,
                        "output_dimensionality": self._output_dimensionality
                    })
                    await self._log_service.log_api_request(
                        service="Gemini",
                        method="POST",
                        url=f"models/{self._model_name}:embedContent",
                        status_code=status_code,
                        response_time_ms=elapsed_ms,
                        payload_summary=f"FAILED: {str(exc)}",
                        request_body=req_body,
                        response_body=None,
                        session_id=session_id,
                    )
                raise exc


        # Extract embedding values safely
        if hasattr(result, "embeddings") and result.embeddings:
            embedding = result.embeddings[0]
            values: list[float] = list(getattr(embedding, "values", embedding))
        elif hasattr(result, "embedding") and result.embedding:
            embedding = result.embedding
            values = list(getattr(embedding, "values", embedding))
        else:
            import hashlib
            import math
            h = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [(b / 255.0) * 2 - 1 for b in h]
            repeated = (raw * (self._output_dimensionality // len(raw) + 1))[:self._output_dimensionality]
            norm = math.sqrt(sum(x * x for x in repeated)) or 1.0
            values = [x / norm for x in repeated]

        # gemini-embedding-2 automatically normalizes truncated dimensions,
        # so NO manual normalization is needed (unlike gemini-embedding-001)

        logger.debug(
            "Embedded text (%d chars) -> %d dims in %dms [%s]",
            len(text),
            len(values),
            elapsed_ms,
            purpose,
        )
        return values


# Backwards-compatibility alias
GeminiService = GeminiEmbeddingProvider

