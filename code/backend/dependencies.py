"""FastAPI Dependency Injection providers."""

from fastapi import Request, Depends
from config import get_settings, Settings
from db.neo4j_service import Neo4jService
from db.mysql_service import MySQLService
from services.log_service import LogService
from services.openalex_service import OpenAlexService
from services.gemini_service import GeminiService
from services.rate_limiter import AdaptiveRateLimiter
from services.crawler_service import CrawlerService
from services.ranking_service import RankingService
from services.graph_search_service import GraphSearchService

def get_neo4j_service(request: Request) -> Neo4jService:
    return request.app.state.neo4j_service

def get_mysql_service(request: Request) -> MySQLService:
    return request.app.state.mysql_service

def get_log_service(mysql: MySQLService = Depends(get_mysql_service)) -> LogService:
    return LogService(mysql)

def get_rate_limiter(settings: Settings = Depends(get_settings)) -> AdaptiveRateLimiter:
    return AdaptiveRateLimiter(initial_rate=settings.openalex_rate_limit)

async def get_openalex_service(
    settings: Settings = Depends(get_settings),
    log_service: LogService = Depends(get_log_service)
):
    service = OpenAlexService(
        api_key=settings.openalex_api_key,
        log_service=log_service
    )
    try:
        yield service
    finally:
        await service.close()

def get_gemini_service(
    settings: Settings = Depends(get_settings),
    log_service: LogService = Depends(get_log_service)
) -> GeminiService:
    return GeminiService(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        log_service=log_service,
        model_name=settings.embedding_model,
    )

def get_crawler_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    log_service: LogService = Depends(get_log_service),
) -> CrawlerService:
    return CrawlerService(neo4j, openalex, rate_limiter, log_service)

def get_ranking_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    mysql: MySQLService = Depends(get_mysql_service),
) -> RankingService:
    return RankingService(neo4j, mysql)

def get_graph_search_service(
    neo4j: Neo4jService = Depends(get_neo4j_service),
    openalex: OpenAlexService = Depends(get_openalex_service),
    gemini: GeminiService = Depends(get_gemini_service),
    crawler: CrawlerService = Depends(get_crawler_service),
    ranking: RankingService = Depends(get_ranking_service),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    log_service: LogService = Depends(get_log_service),
) -> GraphSearchService:
    return GraphSearchService(
        neo4j=neo4j,
        openalex=openalex,
        gemini=gemini,
        crawler=crawler,
        ranking=ranking,
        rate_limiter=rate_limiter,
        log_service=log_service,
    )
