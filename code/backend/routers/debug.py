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

from services.log_service import LogService
from services.openalex_service import OpenAlexService
from services.gemini_service import GeminiService
from dependencies import get_log_service, get_openalex_service, get_gemini_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


# --- Request / Response Models ---

class TestRetrieveRequest(BaseModel):
    """Request body for paper retrieval test."""

    doi: str = Field(..., description="DOI to look up (e.g. '10.1109/SRC65875.2025.11263707')")


class TestRetrieveResponse(BaseModel):
    """Response for paper retrieval test."""

    success: bool
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    year: Optional[int] = None
    cited_by_count: Optional[int] = None
    elapsed_ms: int = 0
    error: Optional[str] = None


class TestEmbedRequest(BaseModel):
    """Request body for text embedding test."""

    text: str = Field(..., min_length=1, description="Text to embed")


class TestEmbedResponse(BaseModel):
    """Response for text embedding test."""

    success: bool
    dimensions: Optional[int] = None
    first_5_values: Optional[list[float]] = None
    elapsed_ms: int = 0
    error: Optional[str] = None


class TestSimilarityRequest(BaseModel):
    """Request body for cosine similarity test."""

    text_a: str = Field(..., min_length=1, description="First text passage")
    text_b: str = Field(..., min_length=1, description="Second text passage")


class TestSimilarityResponse(BaseModel):
    """Response for cosine similarity test."""

    success: bool
    similarity_score: Optional[float] = None
    dimensions: Optional[int] = None
    elapsed_ms: int = 0
    error: Optional[str] = None


# --- Helper ---

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
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
    """Test paper retrieval from OpenAlex by DOI."""
    start = time.monotonic()

    try:
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
    gemini_service: GeminiService = Depends(get_gemini_service),
) -> TestEmbedResponse:
    """Test text embedding via the Gemini API."""
    start = time.monotonic()

    try:
        embedding = await gemini_service.embed_paper(body.text, session_id="debug")
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
    gemini_service: GeminiService = Depends(get_gemini_service),
) -> TestSimilarityResponse:
    """Test cosine similarity between two text passages."""
    start = time.monotonic()

    try:
        emb_a = await gemini_service.embed_paper(body.text_a, session_id="debug")
        emb_b = await gemini_service.embed_paper(body.text_b, session_id="debug")
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
