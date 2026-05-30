from __future__ import annotations
import logging
from typing import Any  # Any: MySQL row values are dynamically typed

import aiomysql

logger = logging.getLogger(__name__)

DDL_STATEMENTS: list[str] = [
    '''CREATE TABLE IF NOT EXISTS sessions (
        session_id VARCHAR(36) PRIMARY KEY,
        seed_doi VARCHAR(255) NOT NULL,
        research_questions JSON NOT NULL,
        similarity_threshold FLOAT NOT NULL DEFAULT 0.5,
        max_depth INT NOT NULL DEFAULT 2,
        mode VARCHAR(20) NOT NULL DEFAULT 'interactive',
        status VARCHAR(20) NOT NULL DEFAULT 'created',
        papers_discovered INT NOT NULL DEFAULT 0,
        papers_relevant INT NOT NULL DEFAULT 0,
        current_depth INT NOT NULL DEFAULT 0,
        full_state JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )''',
    '''CREATE TABLE IF NOT EXISTS settings (
        setting_key VARCHAR(100) PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )''',
    '''CREATE TABLE IF NOT EXISTS api_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        session_id VARCHAR(36),
        service VARCHAR(50) NOT NULL,
        method VARCHAR(10) NOT NULL,
        url TEXT NOT NULL,
        status_code INT,
        response_time_ms INT,
        payload_summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_api_logs_session (session_id),
        INDEX idx_api_logs_service (service),
        INDEX idx_api_logs_created (created_at)
    )''',
    '''CREATE TABLE IF NOT EXISTS app_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        session_id VARCHAR(36),
        level VARCHAR(10) NOT NULL,
        module VARCHAR(100) NOT NULL,
        message TEXT NOT NULL,
        extra JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_app_logs_session (session_id),
        INDEX idx_app_logs_level (level),
        INDEX idx_app_logs_created (created_at)
    )''',
]


class MySQLService:
    """Async MySQL connection pool with DDL and CRUD operations."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        """Create the MySQL connection pool."""
        self._pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            db=self._database,
            autocommit=True,
            minsize=2,
            maxsize=10,
        )
        logger.info('MySQL connection pool created: %s:%d/%s', self._host, self._port, self._database)

    async def close(self) -> None:
        """Close the MySQL connection pool."""
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            logger.info('MySQL connection pool closed')

    @property
    def pool(self) -> aiomysql.Pool:
        if self._pool is None:
            raise RuntimeError('MySQL pool not initialized. Call connect() first.')
        return self._pool

    async def execute(self, query: str, args: tuple[object, ...] | None = None) -> int:
        """Execute a query and return the number of affected rows."""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return cur.rowcount

    async def fetch_one(
        self, query: str, args: tuple[object, ...] | None = None
    ) -> dict[str, Any] | None:  # Any: MySQL column values are dynamically typed
        """Fetch a single row as a dict, or None if no result."""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                row = await cur.fetchone()
                return dict(row) if row else None  # type: ignore[arg-type]

    async def fetch_all(
        self, query: str, args: tuple[object, ...] | None = None
    ) -> list[dict[str, Any]]:  # Any: MySQL column values are dynamically typed
        """Fetch all rows as a list of dicts."""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                rows = await cur.fetchall()
                return [dict(r) for r in rows]  # type: ignore[arg-type]

    async def initialize_schema(self) -> None:
        """Run DDL statements to create tables if they don't exist."""
        for ddl in DDL_STATEMENTS:
            try:
                await self.execute(ddl)
                logger.info('DDL applied: %s...', ddl[:50])
            except Exception as e:
                logger.warning('DDL skipped: %s — %s', ddl[:50], e)
        logger.info('MySQL schema initialization complete')

    async def health_check(self) -> bool:
        """Verify MySQL connectivity. Returns True if healthy."""
        try:
            result = await self.fetch_one('SELECT 1 AS ok')
            return result is not None and result.get('ok') == 1
        except Exception:
            return False

    # --- Session helpers ---

    async def update_session_status(
        self, session_id: str, status: str
    ) -> None:
        """Update the status of a session."""
        await self.execute(
            'UPDATE sessions SET status = %s WHERE session_id = %s',
            (status, session_id),
        )

    async def update_session_progress(
        self,
        session_id: str,
        *,
        papers_discovered: int | None = None,
        papers_relevant: int | None = None,
        current_depth: int | None = None,
        status: str | None = None,
    ) -> None:
        """Update session progress counters."""
        updates: list[str] = []
        params: list[object] = []
        if papers_discovered is not None:
            updates.append('papers_discovered = %s')
            params.append(papers_discovered)
        if papers_relevant is not None:
            updates.append('papers_relevant = %s')
            params.append(papers_relevant)
        if current_depth is not None:
            updates.append('current_depth = %s')
            params.append(current_depth)
        if status is not None:
            updates.append('status = %s')
            params.append(status)
        if not updates:
            return
        params.append(session_id)
        sql = f'UPDATE sessions SET {", ".join(updates)} WHERE session_id = %s'
        await self.execute(sql, tuple(params))

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch a session by ID."""
        return await self.fetch_one(
            'SELECT * FROM sessions WHERE session_id = %s',
            (session_id,),
        )

