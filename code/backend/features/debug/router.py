"""FastAPI debug router for ALRS v2 backend.

Exposes diagnostic endpoints for testing individual subsystems:
- Paper retrieval via OpenAlex
- Text embedding via Gemini
- Cosine similarity between two text passages

All operations are logged at DEBUG level for monitoring via the Logs page.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from features.debug.models import (
    TestRetrieveRequest,
    TestRetrieveResponse,
    TestEmbedRequest,
    TestEmbedResponse,
    TestSimilarityRequest,
    TestSimilarityResponse,
)
from core.logging.log_service import LogService
from core.clients.openalex_client import OpenAlexService
from features.embedding.providers.base import EmbeddingProvider
from core.dependencies import get_log_service, get_openalex_service, get_embedding_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


# --- Helper ---

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Uses the standard formula:  cos(θ) = (A · B) / (‖A‖ × ‖B‖)
    returning a float in the range [-1, 1].  A value of 1 indicates
    identical direction, 0 orthogonality, and -1 opposite direction.

    This is a pure-Python implementation (no NumPy) to avoid adding
    a heavy dependency for a single diagnostic endpoint.

    Args:
        a: First embedding vector (e.g. 768-dimensional).
        b: Second embedding vector, must have the same length as *a*.

    Returns:
        Cosine similarity score in [-1, 1], or ``0.0`` if either
        vector has zero magnitude (degenerate / empty embedding).
    """
    # Dot product: Σ(a_i × b_i)
    dot = sum(x * y for x, y in zip(a, b))
    # L2 norms: ‖a‖ and ‖b‖
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    # Guard against division-by-zero for degenerate embeddings
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --- Endpoints ---

@router.post("/test-retrieve", response_model=TestRetrieveResponse)
async def test_retrieve(
    body: TestRetrieveRequest,
    log_service: LogService = Depends(get_log_service),
    openalex_service: OpenAlexService = Depends(get_openalex_service),
) -> TestRetrieveResponse:
    """Test paper retrieval from OpenAlex by DOI.

    Sends a live request to the OpenAlex REST API and returns the
    resolved paper metadata.  Used by the debug panel so operators
    can verify that the OpenAlex integration (API key, network, etc.)
    is working before starting a real search session.

    Args:
        body: Contains the DOI string to look up.
        log_service: Injected structured-logging service.
        openalex_service: Injected OpenAlex HTTP client.

    Returns:
        ``TestRetrieveResponse`` with paper metadata on success,
        or ``success=False`` with an error message on failure.
        The ``elapsed_ms`` field is always populated for latency
        monitoring.

    Raises:
        No HTTP exceptions — errors are returned *inside* the
        response body so the debug panel can display them inline.
    """
    # monotonic() is preferred over time() for elapsed-time measurement
    # because it is immune to system clock adjustments.
    start = time.monotonic()

    try:
        # "debug" session_id lets log queries filter diagnostic traffic
        paper = await openalex_service.get_paper_by_doi(body.doi, session_id="debug")
        elapsed = int((time.monotonic() - start) * 1000)

        if paper is None:
            await log_service.log(
                level="DEBUG",
                module="debug.retrieve",
                message=f"Paper not found for DOI: {body.doi}",
                extra={"doi": body.doi, "elapsed_ms": elapsed},
            )
            return TestRetrieveResponse(
                success=False,
                elapsed_ms=elapsed,
                error=f"Paper not found for DOI: {body.doi}",
            )

        await log_service.log(
            level="DEBUG",
            module="debug.retrieve",
            message=f"Retrieved paper: {paper.title}",
            extra={
                "doi": paper.doi,
                "title": paper.title,
                "year": paper.year,
                "has_abstract": paper.abstract is not None,
                "elapsed_ms": elapsed,
            },
        )

        return TestRetrieveResponse(
            success=True,
            doi=paper.doi,
            title=paper.title,
            abstract=paper.abstract,
            year=paper.year,
            cited_by_count=paper.cited_by_count,
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        # Catch-all: network errors, JSON parse failures, etc.
        elapsed = int((time.monotonic() - start) * 1000)
        await log_service.log(
            level="DEBUG",
            module="debug.retrieve",
            message=f"Paper retrieval failed: {exc}",
            extra={"doi": body.doi, "error": str(exc), "elapsed_ms": elapsed},
        )
        return TestRetrieveResponse(
            success=False,
            elapsed_ms=elapsed,
            error=str(exc),
        )


@router.post("/test-embed", response_model=TestEmbedResponse)
async def test_embed(
    body: TestEmbedRequest,
    log_service: LogService = Depends(get_log_service),
    gemini_service: EmbeddingProvider = Depends(get_embedding_provider),
) -> TestEmbedResponse:
    """Test text embedding via the Gemini API.

    Sends a single text string to the configured Gemini embedding
    model and returns the vector dimensionality plus a short preview
    (first 5 values).  This lets operators verify that the Gemini
    API key is valid and the embedding pipeline is functional.

    Args:
        body: Contains the raw text to embed (must be non-empty).
        log_service: Injected structured-logging service.
        gemini_service: Injected Gemini embedding client.

    Returns:
        ``TestEmbedResponse`` with vector metadata on success,
        or ``success=False`` with an error description on failure.

    Raises:
        No HTTP exceptions — errors are returned *inside* the
        response body so the debug panel can display them inline.
    """
    start = time.monotonic()

    try:
        # embed_document() handles task-type formatting internally
        embedding = await gemini_service.embed_document(body.text, session_id="debug")
        elapsed = int((time.monotonic() - start) * 1000)

        await log_service.log(
            level="DEBUG",
            module="debug.embed",
            message=f"Embedded text ({len(body.text)} chars) -> {len(embedding)} dims",
            extra={
                "text_length": len(body.text),
                "dimensions": len(embedding),
                "first_5": embedding[:5],
                "elapsed_ms": elapsed,
            },
        )

        # Return only the first 5 values as a sanity-check preview;
        # the full vector stays server-side.
        return TestEmbedResponse(
            success=True,
            dimensions=len(embedding),
            first_5_values=embedding[:5],
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        await log_service.log(
            level="DEBUG",
            module="debug.embed",
            message=f"Embedding failed: {exc}",
            extra={"text_length": len(body.text), "error": str(exc), "elapsed_ms": elapsed},
        )
        return TestEmbedResponse(
            success=False,
            elapsed_ms=elapsed,
            error=str(exc),
        )


@router.post("/test-similarity", response_model=TestSimilarityResponse)
async def test_similarity(
    body: TestSimilarityRequest,
    log_service: LogService = Depends(get_log_service),
    gemini_service: EmbeddingProvider = Depends(get_embedding_provider),
) -> TestSimilarityResponse:
    """Test cosine similarity between two text passages.

    Embeds both passages via Gemini, then computes their cosine
    similarity using :func:`_cosine_similarity`.  This is the most
    comprehensive debug endpoint — it exercises both the embedding
    pipeline *and* the similarity math in a single request.

    Args:
        body: Contains ``text_a`` and ``text_b`` to compare.
        log_service: Injected structured-logging service.
        gemini_service: Injected Gemini embedding client.

    Returns:
        ``TestSimilarityResponse`` with the similarity score
        (rounded to 6 decimal places) and vector dimensions on
        success, or ``success=False`` with an error on failure.

    Raises:
        No HTTP exceptions — errors are returned *inside* the
        response body so the debug panel can display them inline.
    """
    start = time.monotonic()

    try:
        # Embed both passages sequentially (debug traffic is low-volume,
        # so parallelising with asyncio.gather is unnecessary here).
        emb_a = await gemini_service.embed_document(body.text_a, session_id="debug")
        emb_b = await gemini_service.embed_document(body.text_b, session_id="debug")
        score = _cosine_similarity(emb_a, emb_b)
        elapsed = int((time.monotonic() - start) * 1000)

        await log_service.log(
            level="DEBUG",
            module="debug.similarity",
            message=f"Cosine similarity: {score:.4f} ({len(emb_a)} dims)",
            extra={
                "text_a_length": len(body.text_a),
                "text_b_length": len(body.text_b),
                "similarity_score": round(score, 6),
                "dimensions": len(emb_a),
                "elapsed_ms": elapsed,
            },
        )

        # Round to 6 decimal places for stable JSON serialisation
        return TestSimilarityResponse(
            success=True,
            similarity_score=round(score, 6),
            dimensions=len(emb_a),
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        await log_service.log(
            level="DEBUG",
            module="debug.similarity",
            message=f"Similarity test failed: {exc}",
            extra={
                "text_a_length": len(body.text_a),
                "text_b_length": len(body.text_b),
                "error": str(exc),
                "elapsed_ms": elapsed,
            },
        )
        return TestSimilarityResponse(
            success=False,
            elapsed_ms=elapsed,
            error=str(exc),
        )
