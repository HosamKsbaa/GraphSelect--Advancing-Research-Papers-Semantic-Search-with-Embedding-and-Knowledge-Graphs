"""Embeddings engine: gemini-embedding-2 vectors (768 dimensions, L2-normalized).

Public API. Import from `engines.embeddings`, never from its internal modules.
"""

from engines.embeddings.service import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_PROFILE,
    GeminiEmbeddingClient,
    document_text,
    normalize_embedding,
    query_text,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_PROFILE",
    "GeminiEmbeddingClient",
    "document_text",
    "normalize_embedding",
    "query_text",
]
