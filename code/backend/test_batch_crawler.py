import asyncio
import logging
import time

from config import get_settings
from core.db.mysql_service import MySQLService
from core.db.neo4j_service import Neo4jService
from features.search.crawler_service import CrawlerService
from core.logging.log_service import LogService
from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_crawler():
    settings = get_settings()

    neo4j = Neo4jService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await neo4j.connect()

    mysql = MySQLService(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
    )
    await mysql.connect()

    log_service = LogService(mysql)
    openalex = OpenAlexService(
        api_key=settings.openalex_api_key,
        log_service=log_service,
    )
    rate_limiter = AdaptiveRateLimiter(initial_rate=10.0)

    crawler = CrawlerService(
        neo4j=neo4j,
        openalex=openalex,
        rate_limiter=rate_limiter,
        log_service=log_service,
    )

    # Some test DOIs
    test_dois = [
        "10.1109/src65875.2025.11263707", # Seed paper
        "10.1145/3292500.3330919",
        "10.1038/s41586-020-2649-2",
    ]

    session_id = "test-integration-session"

    logger.info(f"Starting batch crawl test for {len(test_dois)} DOIs")
    start_time = time.time()

    async def progress_cb(event):
        logger.info(f"Progress [{event.progress_percent:.1f}%]: {event.message}")

    result = await crawler.run_bfs_cycle(
        session_id=session_id,
        queued_dois=test_dois,
        current_depth=1,
        max_depth=1,
        progress_callback=progress_cb,
    )

    elapsed = time.time() - start_time

    logger.info(f"Crawl Cycle Result:")
    logger.info(f"Papers discovered: {result.papers_discovered}")
    logger.info(f"New papers saved: {result.papers_new}")
    logger.info(f"New DOIs found for next queue: {len(result.new_dois)}")
    logger.info(f"Errors: {len(result.errors)}")
    logger.info(f"Total time taken: {elapsed:.2f} seconds")

    await neo4j.close()
    await mysql.close()

if __name__ == "__main__":
    asyncio.run(test_crawler())
