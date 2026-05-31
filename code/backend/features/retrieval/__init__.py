"""Retrieval feature — paper metadata lookup, remote fetching, and citation graph.

Re-exports for convenience::

    from features.retrieval import RetrievalService, PaperRead, PaperCreate
"""
from features.retrieval.models import (
    AuthorCreate,
    AuthorRead,
    KeywordCreate,
    PaperCreate,
    PaperRead,
    PaperSummary,
    VenueCreate,
    VenueRead,
)
from features.retrieval.service import RetrievalService

__all__ = [
    "AuthorCreate",
    "AuthorRead",
    "KeywordCreate",
    "PaperCreate",
    "PaperRead",
    "PaperSummary",
    "RetrievalService",
    "VenueCreate",
    "VenueRead",
]
