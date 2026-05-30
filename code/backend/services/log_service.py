from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any  # Any: for flexible log extra data

logger = logging.getLogger(__name__)


class LogService:
    """Structured logging service with MySQL persistence."""

    def __init__(self, mysql_service: Any) -> None:  # Any: circular import avoidance
        from db.mysql_service import MySQLService
        self._mysql: MySQLService = mysql_service

    async def log(
        self,
        level: str,
        module: str,
        message: str,
        session_id: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Write a structured log entry to MySQL."""
        try:
            await self._mysql.execute(
                '''INSERT INTO app_logs (session_id, level, module, message, extra)
                   VALUES (%s, %s, %s, %s, %s)''',
                (
                    session_id,
                    level.upper(),
                    module,
                    message,
                    json.dumps(extra) if extra else None,
                ),
            )
        except Exception as e:
            logger.error('Failed to persist log: %s', e)

    async def log_api_request(
        self,
        service: str,
        method: str,
        url: str,
        status_code: int | None = None,
        response_time_ms: int | None = None,
        payload_summary: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record an outgoing API request/response to MySQL."""
        try:
            await self._mysql.execute(
                '''INSERT INTO api_logs
                   (session_id, service, method, url, status_code, response_time_ms, payload_summary)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (
                    session_id,
                    service,
                    method.upper(),
                    url,
                    status_code,
                    response_time_ms,
                    payload_summary,
                ),
            )
        except Exception as e:
            logger.error('Failed to log API request: %s', e)

    async def purge_expired_logs(self, retention_hours: int = 24) -> int:
        """Delete logs older than retention_hours. Returns count of deleted rows."""
        cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        total_deleted = 0
        for table in ('app_logs', 'api_logs'):
            count = await self._mysql.execute(
                f'DELETE FROM {table} WHERE created_at < %s',  # noqa: S608
                (cutoff_str,),
            )
            total_deleted += count
            logger.info('Purged %d expired rows from %s', count, table)
        return total_deleted

    async def get_api_logs(
        self,
        service: str | None = None,
        session_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:  # Any: MySQL row values
        """Query API logs with optional filters."""
        conditions: list[str] = []
        args: list[object] = []
        if service:
            conditions.append('service = %s')
            args.append(service)
        if session_id:
            conditions.append('session_id = %s')
            args.append(session_id)
        if since:
            conditions.append('created_at >= %s')
            args.append(since.strftime('%Y-%m-%d %H:%M:%S'))
        where = ' AND '.join(conditions) if conditions else '1=1'
        query = f'SELECT * FROM api_logs WHERE {where} ORDER BY created_at DESC LIMIT %s'  # noqa: S608
        args.append(limit)
        return await self._mysql.fetch_all(query, tuple(args))

    async def get_app_logs(
        self,
        level: str | None = None,
        module: str | None = None,
        session_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:  # Any: MySQL row values
        """Query application logs with optional filters."""
        conditions: list[str] = []
        args: list[object] = []
        if level:
            conditions.append('level = %s')
            args.append(level.upper())
        if module:
            conditions.append('module = %s')
            args.append(module)
        if session_id:
            conditions.append('session_id = %s')
            args.append(session_id)
        if since:
            conditions.append('created_at >= %s')
            args.append(since.strftime('%Y-%m-%d %H:%M:%S'))
        where = ' AND '.join(conditions) if conditions else '1=1'
        query = f'SELECT * FROM app_logs WHERE {where} ORDER BY created_at DESC LIMIT %s'  # noqa: S608
        args.append(limit)
        return await self._mysql.fetch_all(query, tuple(args))
