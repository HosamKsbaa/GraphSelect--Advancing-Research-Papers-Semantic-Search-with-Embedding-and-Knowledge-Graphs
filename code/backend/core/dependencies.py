"""FastAPI Dependency Injection providers for ALRS v2.

This module is the single source of truth for how services are wired
together. Every provider follows the same pattern:

    1. Receive upstream dependencies via ``Depends()``.
    2. Construct and return the service instance.

Dependency graph (simplified)::

    Request.app.state
        ├── Neo4jService        (core.db)
        └── MySQLService        (core.db)
                └── LogService  (core.logging)
                        ├── OpenAlexService      (core.clients)
                        ├── AdaptiveRateLimiter   (core.clients)
                        └── …
                            ├── RetrievalService          (features.retrieval)
                            ├── GeminiEmbeddingProvider    (features.embedding.providers)
                            ├── PaperEmbeddingService      (features.embedding)
                            ├── CrawlerService             (features.search)
                            ├── RankingService             (features.ranking)
                            ├── GraphSearchService         (features.search)
                            └── SearchSessionService       (features.search)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator
from fastapi import Request, Depends
from config import get_settings, Settings

if TYPE_CHECKING:
    from features.retrieval.service import RetrievalService
    from features.embedding.service import PaperEmbeddingService
    from features.search.crawler_service import CrawlerService
    from features.ranking.service import RankingService
    from features.search.graph_search_service import GraphSearchService
    from features.search.session_service import SearchSessionService
    from features.chat.service import ChatService


# ── Core infrastructure ──────────────────────────────────────────────
from core.db.neo4j_service import Neo4jService
from core.db.mysql_service import MySQLService
from core.logging.log_service import LogService
from core.logging.progress_service import ProgressService
from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter

# ── Feature services (Base types only to avoid circular imports) ─────
from features.embedding.providers.base import EmbeddingProvider


# ── Core infrastructure (from app.state) ─────────────────────────────

def get_neo4j_service(request: Request) -> Neo4jService:
    """Retrieve the Neo4j service singleton from application state."""
    service = getattr(request.app.state, "neo4j_service", None)
    if service is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )
    return service  # type: ignore[no-any-return]


def get_mysql_service(request: Request) -> MySQLService:
    """Retrieve the MySQL service singleton from application state."""
    service = getattr(request.app.state, "mysql_service", None)
    if service is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL service not initialized",
        )
    return service  # type: ignore[no-any-return]


def get_progress_service(request: Request) -> ProgressService:
    """Retrieve or construct the ProgressService singleton from application state."""
    service = getattr(request.app.state, "progress_service", None)
    if service is None:
        service = ProgressService()
        request.app.state.progress_service = service
    return service  # type: ignore[no-any-return]


# ── Cross-cutting concerns ───────────────────────────────────────────

def get_log_service(mysql: MySQLService = Depends(get_mysql_service)) -> LogService:
    """Create a LogService backed by the MySQL connection."""
    return LogService(mysql)


def get_rate_limiter(settings: Settings = Depends(get_settings)) -> AdaptiveRateLimiter:
    """Create an adaptive rate limiter tuned to the OpenAlex rate limit."""
    return AdaptiveRateLimiter(initial_rate=settings.openalex_rate_limit)


# ── External API clients ─────────────────────────────────────────────

async def get_openalex_service(
    settings: Settings = Depends(get_settings),
    log_service: LogService = Depends(get_log_service),
) -> AsyncIterator[OpenAlexService]:
    """Yield an OpenAlexService, ensuring the HTTP session is closed on teardown."""
    service = OpenAlexService(
        api_key=settings.openalex_api_key,
        log_service=log_service,
    )
    try:
        yield service
    finally:
        await service.close()


# ── Embedding providers ──────────────────────────────────────────────

def get_embedding_provider(
    settings: Settings = Depends(get_settings),
    log_service: LogService = Depends(get_log_service),
) -> EmbeddingProvider:
    """Create the active embedding provider (currently Gemini).

    To add a new provider (e.g. OpenAI), add an ``EMBEDDING_PROVIDER``
    config field and branch here.
    """
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
    return GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        log_service=log_service,
        model_name=settings.embedding_model,
    )


# ── Feature services ─────────────────────────────────────────────────

def get_retrieval_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    log_service: LogService = Depends(get_log_service),
) -> RetrievalService:
    """Create the unified retrieval facade (papers, citations, authors, venues)."""
    from features.retrieval.service import RetrievalService
    return RetrievalService(neo4j=neo4j, openalex=openalex, log_service=log_service)


def get_paper_embedding_service(
    provider: EmbeddingProvider = Depends(get_embedding_provider),
    neo4j: Neo4jService = Depends(get_neo4j_service),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    log_service: LogService = Depends(get_log_service),
) -> PaperEmbeddingService:
    """Create the provider-agnostic paper embedding orchestrator."""
    from features.embedding.service import PaperEmbeddingService
    return PaperEmbeddingService(
        neo4j=neo4j,
        provider=provider,
        rate_limiter=rate_limiter,
    )


def get_crawler_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    log_service: LogService = Depends(get_log_service),
) -> CrawlerService:
    """Create the BFS crawler that traverses OpenAlex citations."""
    from features.search.crawler_service import CrawlerService
    return CrawlerService(neo4j, openalex, rate_limiter, log_service)


def get_ranking_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    mysql: MySQLService = Depends(get_mysql_service),
) -> RankingService:
    """Create the ranking service (semantic similarity + PageRank)."""
    from features.ranking.service import RankingService
    return RankingService(neo4j, mysql)


# ── Orchestrators / Facades ──────────────────────────────────────────

def get_graph_search_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    gemini: EmbeddingProvider = Depends(get_embedding_provider),
    crawler: CrawlerService = Depends(get_crawler_service),
    ranking: RankingService = Depends(get_ranking_service),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    log_service: LogService = Depends(get_log_service),
) -> GraphSearchService:
    """Create the top-level BFS orchestrator (crawl → embed → rank)."""
    from features.search.graph_search_service import GraphSearchService
    return GraphSearchService(
        neo4j=neo4j,
        openalex=openalex,
        gemini=gemini,
        crawler=crawler,
        ranking=ranking,
        rate_limiter=rate_limiter,
        log_service=log_service,
    )


def get_search_session_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    mysql: MySQLService = Depends(get_mysql_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
) -> SearchSessionService:
    """Create the session lifecycle service (create → enqueue → stream)."""
    from features.search.session_service import SearchSessionService
    return SearchSessionService(neo4j=neo4j, mysql=mysql, openalex=openalex)


# ── Feature services: Chat ───────────────────────────────────────────

def get_chat_service(
    request: Request,
    mysql: MySQLService = Depends(get_mysql_service),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> ChatService:
    """Create the project-scoped ChatService wired to MySQL, Neo4j, and LLMService."""
    from features.chat.service import ChatService
    llm_service = getattr(request.app.state, "llm_service", None)
    return ChatService(mysql_service=mysql, neo4j_service=neo4j, llm_service=llm_service)


