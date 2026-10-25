"""Gemini embedding calls using an application-owned native SDK client.

Ported from the audited archive (`alrs_tool/search/embedding_client.py`, commit 865cd08).
Profile and text formats follow `.agents/rules/gemini_embeddings.md`.
"""
import asyncio
import math
import httpx
from google.genai.client import AsyncClient
from google.genai.errors import APIError
from google.genai.types import Content, EmbedContentConfig, HttpOptions, HttpRetryOptions, Part
from engines.errors import ProviderError

EMBEDDING_DIMENSIONS = 768
# Vectors are comparable only within one profile: same model, dimensions and text format.
EMBEDDING_PROFILE = "gemini-embedding-2:768:retrieval-v1"


def query_text(question: str) -> str:
    """Format a research question as the documented gemini-embedding-2 retrieval query."""
    return f"task: search result | query: {question}"


def document_text(title: str, abstract: str) -> str:
    """Format a paper as the documented gemini-embedding-2 retrieval document."""
    return f"title: {title} | text: {abstract}"


def normalize_embedding(values: list[float]) -> list[float]:
    if len(values) != EMBEDDING_DIMENSIONS or not all(math.isfinite(value) for value in values):
        raise ProviderError("invalid_embedding", "Gemini returned an invalid 768-dimensional embedding.")
    length = math.sqrt(sum(value * value for value in values))
    if length == 0:
        raise ProviderError("invalid_embedding", "Gemini returned an empty embedding direction.")
    return [value / length for value in values]


class GeminiEmbeddingClient:
    def __init__(self, client: AsyncClient | None, model_name: str = "gemini-embedding-2") -> None:
        self.client = client
        self.model_name = model_name

    async def embed_text(self, text: str) -> list[float]:
        if self.client is None:
            raise ProviderError("embedding_not_configured", "Set the Gemini credentials before running full ALRS search.")
        if self.model_name != "gemini-embedding-2":
            raise ProviderError("embedding_model_unsupported", "Full ALRS currently supports the versioned gemini-embedding-2 profile.")
        # A byte-based upper estimate avoids truncating long abstracts or sending oversized inputs.
        if len(text.encode("utf-8")) > 8192:
            raise ProviderError("embedding_context_limit", "This abstract is too long for the conservative embedding input limit; it was saved without a score.")
        try:
            async with asyncio.timeout(30):
                response = await self.client.models.embed_content(model=self.model_name,
                    contents=Content(parts=[Part(text=text)]), config=EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIMENSIONS,
                        http_options=HttpOptions(timeout=30000, retry_options=HttpRetryOptions(attempts=1))))
        except (APIError, TimeoutError, httpx.TransportError) as error:
            raise ProviderError("embedding_provider_failed", "Gemini could not calculate the paper scores; saved papers remain available.") from error
        if response.embeddings is None or len(response.embeddings) != 1 or response.embeddings[0].values is None:
            raise ProviderError("invalid_embedding", "Gemini did not return one complete embedding.")
        return normalize_embedding(response.embeddings[0].values)
