"""Service registry for agent tools.

Provides a singleton container that holds references to all backend
services required by agent tool functions. Supports explicit initialization
at startup, or automatic, on-demand lazy initialization when attributes
are first accessed.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.clients.openalex_client import OpenAlexService
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService
    from core.logging.log_service import LogService
    from core.paper_retrieval.service import PaperRetrievalService
    from features.embedding.providers.base import EmbeddingProvider


class ServiceRegistryMeta(type):
    """Metaclass that intercepts attribute access on ServiceRegistry to lazily initialize services."""

    def __getattr__(cls, name: str) -> Any:
        if name in (
            "neo4j",
            "openalex",
            "paper_retrieval",
            "llm",
            "log_service",
            "embedding_provider",
            "planning_service",
            "writing_service",
            "export_service",
        ):
            cls._ensure_initialized()
            return getattr(cls, f"_{name}")
        raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")


class ServiceRegistry(metaclass=ServiceRegistryMeta):
    """Singleton container for backend services used by agent tools.

    Supports both explicit startup-time initialization via :meth:`initialize`
    and automatic, on-demand lazy initialization when attributes are accessed.
    """

    _neo4j: Neo4jService
    _openalex: OpenAlexService
    _paper_retrieval: PaperRetrievalService
    _llm: LLMService
    _log_service: LogService
    _embedding_provider: EmbeddingProvider
    _planning_service: Any
    _writing_service: Any
    _export_service: Any

    _initialized: bool = False
    _initializing: bool = False

    @classmethod
    def initialize(
        cls,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        paper_retrieval: PaperRetrievalService,
        llm: LLMService,
        log_service: LogService,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        """Explicitly wire up all service references.

        Args:
            neo4j: Neo4j graph database service.
            openalex: OpenAlex API client.
            paper_retrieval: Atomic paper retrieval pipeline.
            llm: Gemini LLM completion service.
            log_service: Structured logging and agent tracing service.
            embedding_provider: Text embedding provider.
        """
        cls._neo4j = neo4j
        cls._openalex = openalex
        cls._paper_retrieval = paper_retrieval
        cls._llm = llm
        cls._log_service = log_service
        cls._embedding_provider = embedding_provider
        cls._initialized = True

    @classmethod
    def is_initialized(cls) -> bool:
        """Check whether the registry has been initialized."""
        return cls._initialized

    def __getattr__(self, name: str) -> Any:
        """Delegate instance attribute access to the class-level metaclass handler."""
        return getattr(type(self), name)


    @classmethod
    def _ensure_initialized(cls) -> None:
        """Perform on-demand lazy initialization if not already initialized."""
        if cls._initialized:
            return

        if cls._initializing:
            return

        cls._initializing = True
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Initializing ServiceRegistry on-demand...")

            from config import get_settings
            from core.db.neo4j_service import Neo4jService
            from core.db.mysql_service import MySQLService
            from core.logging.log_service import LogService
            from core.clients.openalex_client import OpenAlexService
            from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
            from core.llm.service import LLMService
            from core.paper_retrieval.service import PaperRetrievalService

            settings = get_settings()

            # 1. Neo4j
            neo4j = Neo4jService(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
            )
            # Create the driver immediately
            from neo4j import AsyncGraphDatabase
            neo4j._driver = AsyncGraphDatabase.driver(
                neo4j._uri,
                auth=(neo4j._user, neo4j._password),
            )
            logger.info("ServiceRegistry: Neo4j driver created")

            # 2. MySQL
            mysql = MySQLService(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                database=settings.mysql_database,
            )
            # Since create_pool is async, we schedule it or run it in current loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            async def init_mysql_pool():
                try:
                    await mysql.connect()
                    await mysql.initialize_schema()
                except Exception as e:
                    logger.error("ServiceRegistry: Failed to connect or init MySQL: %s", e)

            if loop.is_running():
                loop.create_task(init_mysql_pool())
            else:
                loop.run_until_complete(init_mysql_pool())

            # 3. LogService
            log_service = LogService(mysql)

            # 4. OpenAlexService
            openalex = OpenAlexService(
                api_key=settings.openalex_api_key,
                log_service=log_service,
            )

            # 5. EmbeddingProvider
            embedding_provider = GeminiEmbeddingProvider(
                api_key=settings.gemini_api_key,
                output_dimensionality=settings.embedding_dimensions,
                log_service=log_service,
                model_name=settings.embedding_model,
            )

            # 6. LLMService
            llm = LLMService(
                api_key=settings.gemini_api_key,
                model_name=settings.adk_model_name,
                log_service=log_service,
            )

            # 7. PaperRetrievalService
            paper_retrieval = PaperRetrievalService(
                neo4j=neo4j,
                openalex=openalex,
                embedding_provider=embedding_provider,
                log_service=log_service,
                projects_dir=settings.projects_dir,
            )

            cls.initialize(
                neo4j=neo4j,
                openalex=openalex,
                paper_retrieval=paper_retrieval,
                llm=llm,
                log_service=log_service,
                embedding_provider=embedding_provider,
            )

            # 8. Domain services (constructed after core services)
            from features.planning.service import PlanningService
            from features.writing.service import WritingService
            from features.export.service import ExportService

            cls._planning_service = PlanningService(
                neo4j=neo4j,
                llm=llm,
                projects_dir=settings.projects_dir,
            )
            cls._writing_service = WritingService(
                neo4j=neo4j,
                llm=llm,
                log_service=log_service,
                projects_dir=settings.projects_dir,
            )
            cls._export_service = ExportService(
                neo4j=neo4j,
                log_service=log_service,
                projects_dir=settings.projects_dir,
            )

            logger.info("ServiceRegistry: on-demand initialization complete")
        except Exception as e:
            cls._initializing = False
            import logging
            logging.getLogger(__name__).exception("ServiceRegistry: Failed lazy initialization: %s", e)
            raise


registry = ServiceRegistry()

