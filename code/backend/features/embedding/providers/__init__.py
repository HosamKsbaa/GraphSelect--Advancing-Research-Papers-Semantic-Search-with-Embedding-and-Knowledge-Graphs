"""Embedding providers — pluggable backends for vector generation.

Re-exports for convenience::

    from features.embedding.providers import EmbeddingProvider, GeminiEmbeddingProvider
"""
from features.embedding.providers.base import EmbeddingProvider
from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider

__all__ = ["EmbeddingProvider", "GeminiEmbeddingProvider"]
