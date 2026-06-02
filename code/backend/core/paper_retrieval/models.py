"""Paper retrieval Pydantic models for the agentic workflow.

Complements the existing ``features.retrieval.models`` with richer
metadata shapes used by the atomic ``PaperRetrievalService`` pipeline.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PaperMetadata(BaseModel):
    """Rich paper metadata aggregated from OpenAlex.

    Extends beyond the basic ``PaperCreate`` model with author names,
    venue, and citation/reference DOI lists.
    """

    doi: str = Field(..., description="Paper DOI")
    title: str = Field(..., description="Paper title")
    abstract: str | None = Field(default=None, description="Paper abstract text")
    year: int | None = Field(default=None, description="Publication year")
    type: str | None = Field(default=None, description="Work type (e.g. 'journal-article')")
    authors: list[str] = Field(default_factory=list, description="Author display names")
    venue: str | None = Field(default=None, description="Publication venue name")
    references: list[str] = Field(default_factory=list, description="Referenced DOIs")
    citations: list[str] = Field(default_factory=list, description="Citing DOIs")


class FullPaper(BaseModel):
    """Complete paper representation returned by the atomic retrieval pipeline.

    Wraps metadata with embedding and scoring information, plus a flag
    indicating whether the paper already existed in the graph.
    """

    metadata: PaperMetadata
    embedding: list[float] | None = Field(
        default=None,
        description="Abstract embedding vector (only set during retrieval, not stored in responses)",
    )
    similarity_scores: list[dict[str, object]] | None = Field(
        default=None,
        description="Similarity scores against research questions",
    )
    already_existed: bool = Field(
        default=False,
        description="True if the paper was already in the graph before this retrieval",
    )
