"""Embedding feature — provider-agnostic paper and question embedding.

Re-exports for convenience::

    from features.embedding import PaperEmbeddingService
"""
from features.embedding.service import PaperEmbeddingService

__all__ = ["PaperEmbeddingService"]
