from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta, timezone
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
                    json.dumps(extra, default=str) if extra else None,
                ),
            )
        except Exception as e:
            logger.error('Failed to persist log: %s', e)
            logger.warning(
                '[FALLBACK APP LOG] session_id=%s level=%s module=%s message=%s extra=%s',
                session_id,
                level,
                module,
                message,
                extra,
            )

    async def log_api_request(
        self,
        service: str,
        method: str,
        url: str,
        status_code: int | None = None,
        response_time_ms: int | None = None,
        payload_summary: str | None = None,
        request_body: str | None = None,
        response_body: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record an outgoing API request/response to MySQL."""
        try:
            canonical_service = {
                "openalex": "OpenAlex",
                "gemini": "Gemini",
            }.get(service.lower(), service)
            await self._mysql.execute(
                '''INSERT INTO api_logs
                   (session_id, service, method, url, status_code, response_time_ms, payload_summary, request_body, response_body)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    session_id,
                    canonical_service,
                    method.upper(),
                    url,
                    status_code,
                    response_time_ms,
                    payload_summary,
                    request_body,
                    response_body,
                ),
            )
        except Exception as e:
            logger.error('Failed to log API request: %s', e)
            logger.warning(
                '[FALLBACK API LOG] session_id=%s service=%s method=%s url=%s status_code=%s response_time_ms=%s payload_summary=%s',
                session_id,
                service,
                method,
                url,
                status_code,
                response_time_ms,
                payload_summary,
            )

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
            conditions.append('LOWER(service) = %s')
            args.append(service.lower())
        if session_id:
            conditions.append('session_id = %s')
            args.append(session_id)
        if since:
            since_utc = since.astimezone(timezone.utc) if since.tzinfo is not None else since
            conditions.append('created_at >= %s')
            args.append(since_utc.strftime('%Y-%m-%d %H:%M:%S'))
        where = ' AND '.join(conditions) if conditions else '1=1'
        
        # Use ASC when 'since' is provided to prevent dropping active logs due to limit
        order_dir = 'ASC' if since else 'DESC'
        query = f'SELECT * FROM api_logs WHERE {where} ORDER BY created_at {order_dir} LIMIT %s'  # noqa: S608
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
            conditions.append('UPPER(level) = %s')
            args.append(level.upper())
        if module:
            conditions.append('module = %s')
            args.append(module)
        if session_id:
            conditions.append('session_id = %s')
            args.append(session_id)
        if since:
            since_utc = since.astimezone(timezone.utc) if since.tzinfo is not None else since
            conditions.append('created_at >= %s')
            args.append(since_utc.strftime('%Y-%m-%d %H:%M:%S'))
        where = ' AND '.join(conditions) if conditions else '1=1'
        
        # Use ASC when 'since' is provided to prevent dropping active logs due to limit
        order_dir = 'ASC' if since else 'DESC'
        query = f'SELECT * FROM app_logs WHERE {where} ORDER BY created_at {order_dir} LIMIT %s'  # noqa: S608
        args.append(limit)
        return await self._mysql.fetch_all(query, tuple(args))
