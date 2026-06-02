"""ALRS v2 paper retrieval module.

Provides the ``PaperRetrievalService`` for atomic paper ingestion and
the ``PaperMetadata`` / ``FullPaper`` models for rich paper representations.
"""
from __future__ import annotations

from core.paper_retrieval.models import FullPaper, PaperMetadata
from core.paper_retrieval.service import PaperRetrievalService

__all__ = [
    "FullPaper",
    "PaperMetadata",
    "PaperRetrievalService",
]
