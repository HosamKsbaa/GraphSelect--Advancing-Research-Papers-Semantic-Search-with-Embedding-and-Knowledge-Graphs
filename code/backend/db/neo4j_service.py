from __future__ import annotations
import logging
from typing import Any  # Only for neo4j Record type boundary
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable, AuthError

logger = logging.getLogger(__name__)


class Neo4jService:
    """Async Neo4j driver wrapper with connection pool management."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Initialize the Neo4j driver and verify connectivity."""
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        await self._driver.verify_connectivity()
        logger.info('Neo4j connection established: %s', self._uri)

    async def close(self) -> None:
        """Close the Neo4j driver and release resources."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info('Neo4j connection closed')

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError('Neo4j driver not initialized. Call connect() first.')
        return self._driver

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a read-only Cypher query and return results as dicts."""
        async with self.driver.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records  # type: ignore[return-value]

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a write Cypher query within a transaction."""
        async with self.driver.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records  # type: ignore[return-value]

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a Cypher query (auto-detects read/write)."""
        return await self.execute_write(query, parameters, database)

    async def health_check(self) -> bool:
        """Verify Neo4j connectivity. Returns True if healthy."""
        try:
            await self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, AuthError, RuntimeError):
            return False
