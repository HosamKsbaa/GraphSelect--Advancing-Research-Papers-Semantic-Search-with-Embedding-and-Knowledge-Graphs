"""FastAPI dependency injection providers for ALRS v2 backend.

Provides singleton retrieval and factory functions for application state,
database services (Pure Neo4j & SQLite Telemetry; Strictly Zero MySQL),
logging, rate limiters, and feature-level services.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Any

from fastapi import Depends, Request

from config import Settings, get_settings

if TYPE_CHECKING:
    from features.embedding.service import PaperEmbeddingService
    from features.ranking.service import RankingService
    from features.retrieval.service import RetrievalService
    from features.search.crawler_service import CrawlerService
    from features.search.graph_search_service import GraphSearchService
    from features.search.session_service import SearchSessionService
    from features.chat.service import ChatService


# ── Core infrastructure ──────────────────────────────────────────────
from core.db.neo4j_service import Neo4jService
from core.logging.log_service import LogService
from core.logging.progress_service import ProgressService
from core.logging.telemetry_service import TelemetryService
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


def get_telemetry_service(request: Request) -> TelemetryService:
    """Retrieve or construct TelemetryService from application state."""
    service = getattr(request.app.state, "telemetry_service", None)
    if service is None:
        service = TelemetryService()
        request.app.state.telemetry_service = service
    return service  # type: ignore[no-any-return]


def get_progress_service(request: Request) -> ProgressService:
    """Retrieve or construct the ProgressService singleton from application state."""
    service = getattr(request.app.state, "progress_service", None)
    if service is None:
        service = ProgressService()
        request.app.state.progress_service = service
    return service  # type: ignore[no-any-return]


# ── Cross-cutting concerns ───────────────────────────────────────────

def get_log_service(telemetry: TelemetryService = Depends(get_telemetry_service)) -> LogService:
    """Create a LogService backed by standard logging and SQLite telemetry."""
    return LogService(telemetry_service=telemetry)


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
    """Create the active embedding provider (currently Gemini)."""
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
) -> RankingService:
    """Create the ranking service (semantic similarity + PageRank)."""
    from features.ranking.service import RankingService
    return RankingService(neo4j)


# ── Orchestrators / Facades ──────────────────────────────────────────

def get_graph_search_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    gemini: Any = Depends(get_embedding_provider),
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
    openalex: OpenAlexService = Depends(get_openalex_service),
) -> SearchSessionService:
    """Create the session lifecycle service (create → enqueue → stream)."""
    from features.search.session_service import SearchSessionService
    return SearchSessionService(neo4j=neo4j, openalex=openalex)


# ── Feature services: Chat ───────────────────────────────────────────

def get_chat_service(
    request: Request,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> ChatService:
    """Create the project-scoped ChatService wired to Neo4j and LLMService."""
    from features.chat.service import ChatService
    llm_service = getattr(request.app.state, "llm_service", None)
    return ChatService(neo4j_service=neo4j, llm_service=llm_service)
