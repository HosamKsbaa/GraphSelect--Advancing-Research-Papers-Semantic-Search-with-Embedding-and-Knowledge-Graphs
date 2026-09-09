"""Gemini embedding provider for ALRS v2.

Connects to Google's Gemini API (gemini-embedding-2) to generate vector
embeddings for academic paper abstracts and research questions.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any, cast

from google import genai
from google.genai import types

from features.embedding.providers.base import EmbeddingProvider

if TYPE_CHECKING:
    from core.logging.log_service import LogService


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Generates text embeddings using Google's Gemini API."""

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

        self._output_dimensionality = output_dimensionality
        self._log_service = log_service
        self._model_name = model_name
        self._client: genai.Client | None = None

        # Choose connection mode: Google Cloud Vertex AI or Google AI Studio
        use_vertex = vertexai if vertexai is not None else settings.use_vertex_ai
        if use_vertex:
            self._client = self._init_vertex_client(settings, project, location)
        else:
            self._client = self._init_studio_client(settings, api_key)

    def _init_vertex_client(
        self,
        settings: Any,
        project: str | None,
        location: str | None,
    ) -> genai.Client | None:
        """Initialize Google Cloud Vertex AI client."""
        gcp_project = project or settings.vertex_project or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
        gcp_location = location or settings.vertex_location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"

        clean_project = gcp_project.strip()
        if not clean_project or clean_project in {"None", "null"}:
            return None
        return genai.Client(vertexai=True, project=clean_project, location=gcp_location.strip())

    def _init_studio_client(self, settings: Any, api_key: str | None) -> genai.Client | None:
        """Initialize Google AI Studio client with an API key."""
        key = (
            api_key
            or settings.gemini_api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        clean_key = key.strip()
        if not clean_key or clean_key in {"None", "null", "your_gemini_api_key_here"}:
            return None
        return genai.Client(api_key=clean_key, vertexai=False)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._output_dimensionality

    # ── 1. Text Formatting for Gemini ─────────────────────────────────

    @staticmethod
    def _format_document(text: str, title: str | None = None) -> str:
        """Format a paper as a retrieval document: 'title: ... | text: ...'"""
        safe_title = title.strip() if title else "none"
        return f"title: {safe_title} | text: {text}"

    @staticmethod
    def _format_query(query: str, task: str = "question answering") -> str:
        """Format a research question as a retrieval query."""
        return f"task: {task} | query: {query}"

    # ── 2. Public Methods (Single & Batch) ────────────────────────────

    async def embed_document(
        self,
        text: str,
        title: str | None = None,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a single paper abstract."""
        results = await self.batch_embed_documents([(text, title)], session_id=session_id)
        if not results:
            raise RuntimeError("Gemini API failed to return an embedding for document.")
        return results[0]

    embed_paper = embed_document

    async def embed_query(
        self,
        query: str,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a research question for vector similarity search."""
        formatted = self._format_query(query)
        results = await self._embed_batch([formatted], session_id=session_id)
        if not results:
            raise RuntimeError("Gemini API failed to return an embedding for query.")
        return results[0]

    embed_question = embed_query

    async def batch_embed_documents(
        self,
        documents: list[tuple[str, str | None]],
        *,
        session_id: str | None = None,
        batch_size: int = 50,
    ) -> list[list[float]]:
        """Embed multiple paper abstracts in chunks of up to 50."""
        if not documents:
            return []

        all_embeddings: list[list[float]] = []

        # Send papers to Google in safe chunks of 50 per API call
        for start in range(0, len(documents), batch_size):
            chunk = documents[start : start + batch_size]
            formatted_chunk = [
                self._format_document(text, title)
                for text, title in chunk
            ]
            chunk_vectors = await self._embed_batch(formatted_chunk, session_id=session_id)
            all_embeddings.extend(chunk_vectors)

        return all_embeddings

    # ── 3. Core Network Call with Retry & Telemetry ───────────────────

    async def _embed_batch(
        self,
        formatted_texts: list[str],
        session_id: str | None = None,
    ) -> list[list[float]]:
        """Send formatted texts to Google and return their vector embeddings."""
        if not formatted_texts:
            return []

        # Fail loudly if API credentials are not configured
        if self._client is None:
            raise RuntimeError(
                "Gemini API client is not initialized. Please configure GEMINI_API_KEY or Google Cloud Vertex AI credentials."
            )

        start_time_ms = int(time.monotonic() * 1000)

        try:
            response = await self._call_gemini_with_retry(formatted_texts)
            elapsed_ms = int(time.monotonic() * 1000) - start_time_ms

            await self._log_telemetry(
                count=len(formatted_texts),
                status_code=200,
                elapsed_ms=elapsed_ms,
                session_id=session_id,
            )

            return self._extract_vectors_from_response(response, formatted_texts)

        except Exception as error:
            elapsed_ms = int(time.monotonic() * 1000) - start_time_ms
            status_code = getattr(error, "code", getattr(error, "status_code", 500))

            await self._log_telemetry(
                count=len(formatted_texts),
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                session_id=session_id,
                error_message=str(error),
            )
            raise error

    async def _call_gemini_with_retry(self, texts: list[str]) -> Any:
        """Execute the Google API call on a worker thread with auto-retry on 429."""
        if self._client is None:
            raise RuntimeError(
                "Gemini API client is not initialized. Please configure GEMINI_API_KEY or Google Cloud Vertex AI credentials."
            )

        max_attempts = 4  # Initial try + up to 3 retries

        for attempt in range(max_attempts):
            try:
                # Run the blocking Google SDK call in a background thread
                return await asyncio.to_thread(
                    self._client.models.embed_content,
                    model=self._model_name,
                    contents=cast(Any, texts),
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._output_dimensionality,
                    ),
                )
            except Exception as error:
                status_code = getattr(error, "code", getattr(error, "status_code", 500))

                # If Google returned Rate Limit (429) and retries remain: wait and retry
                is_rate_limit = (status_code == 429)
                can_retry = (attempt < max_attempts - 1)

                if is_rate_limit and can_retry:
                    sleep_seconds = 2 ** attempt  # Wait 1s, 2s, 4s
                    await asyncio.sleep(sleep_seconds)
                    continue

                raise error

    def _extract_vectors_from_response(
        self,
        response: Any,
        texts: list[str],
    ) -> list[list[float]]:
        """Extract floating-point vectors from Google's response object."""
        raw_embeddings = getattr(response, "embeddings", None)
        if not raw_embeddings:
            single = getattr(response, "embedding", None)
            raw_embeddings = [single] if single else []

        if len(raw_embeddings) < len(texts):
            raise ValueError(
                f"Gemini API returned {len(raw_embeddings)} embeddings for {len(texts)} inputs."
            )

        vectors: list[list[float]] = []

        for index, emb_item in enumerate(raw_embeddings):
            values = getattr(emb_item, "values", emb_item)
            if not hasattr(values, "__iter__"):
                raise ValueError(
                    f"Gemini API response embedding at index {index} has no vector values."
                )
            vectors.append([float(v) for v in values])

        return vectors

    # ── 4. Telemetry Logging ─────────────────────────────────────────

    async def _log_telemetry(
        self,
        count: int,
        status_code: int,
        elapsed_ms: int,
        session_id: str | None,
        error_message: str | None = None,
    ) -> None:
        """Record API performance metrics for the thesis evaluation dashboard."""
        if not self._log_service:
            return

        if error_message:
            summary = f"FAILED: {error_message}"
        else:
            summary = f"items={count}, dims={self._output_dimensionality}"

        await self._log_service.log_api_request(
            service="Gemini",
            method="POST",
            url=f"models/{self._model_name}:embedContent",
            status_code=status_code,
            response_time_ms=elapsed_ms,
            payload_summary=summary,
            session_id=session_id,
        )


# Backward-compatibility alias
GeminiService = GeminiEmbeddingProvider
