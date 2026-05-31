"""Pydantic request/response models for the debug feature."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
