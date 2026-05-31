"""Abstract base class for embedding providers.

All embedding backends (Gemini, OpenAI, local models, etc.) must implement
this interface so that ``PaperEmbeddingService`` remains provider-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Provider-agnostic embedding interface.

    Subclasses MUST implement :meth:`embed_document` and :meth:`embed_query`.
    They SHOULD expose :attr:`model_name` and :attr:`dimensions` for
    telemetry and storage metadata.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the canonical model identifier (e.g. ``'gemini-embedding-2'``)."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the output dimensionality of the embedding vectors."""
        ...

    @abstractmethod
    async def embed_document(
        self,
        text: str,
        title: str | None = None,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a document (paper abstract) for retrieval indexing.

        Args:
            text: Document body text (abstract).
            title: Optional document title for asymmetric retrieval formatting.
            session_id: Optional session identifier for telemetry.

        Returns:
            Embedding vector as a list of floats.
        """
        ...

    @abstractmethod
    async def embed_query(
        self,
        query: str,
        *,
        session_id: str | None = None,
    ) -> list[float]:
        """Embed a query (research question) for retrieval search.

        Args:
            query: The research question or search query text.
            session_id: Optional session identifier for telemetry.

        Returns:
            Embedding vector as a list of floats.
        """
        ...
