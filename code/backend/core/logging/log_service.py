from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any  # Any: for flexible log extra data

logger = logging.getLogger(__name__)


class LogService:
    """Structured logging service decoupled from MySQL, directing events to logger/telemetry."""

    def __init__(self, backend_service: Any = None, telemetry_service: Any = None) -> None:
        self._mysql: Any = backend_service
        self._telemetry: Any = telemetry_service

    async def log(
        self,
        level: str,
        module: str,
        message: str,
        session_id: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Write a structured log entry."""
        if self._mysql is not None and hasattr(self._mysql, "execute"):
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
                return
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
                return

        # Pure decoupled logging mode (Zero MySQL)
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger.log(lvl, "[%s] [%s] %s | extra=%s", module, session_id or "global", message, extra)

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
        """Record an outgoing API request/response."""
        if self._mysql is not None and hasattr(self._mysql, "execute"):
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
                return
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
                return

        # Pure decoupled logging mode (Zero MySQL)
        logger.info(
            "[API LOG] service=%s method=%s url=%s status=%s latency=%sms",
            service, method, url, status_code, response_time_ms,
        )

    async def purge_expired_logs(self, retention_hours: int = 24) -> int:
        """Delete logs older than retention_hours. Returns count of deleted rows."""
        if self._mysql is not None and hasattr(self._mysql, "execute"):
            cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
            cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
            total_deleted = 0
            for table in ('app_logs', 'api_logs'):
                count = await self._mysql.execute(
                    f'DELETE FROM {table} WHERE created_at < %s',
                    (cutoff_str,),
                )
                total_deleted += count
                logger.info('Purged %d expired rows from %s', count, table)
            return total_deleted
        return 0

    async def get_api_logs(
        self,
        service: str | None = None,
        session_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query API logs with optional filters."""
        if self._mysql is not None and hasattr(self._mysql, "fetch_all"):
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
            order_dir = 'ASC' if since else 'DESC'
            query = f'SELECT * FROM api_logs WHERE {where} ORDER BY created_at {order_dir} LIMIT %s'
            args.append(limit)
            return await self._mysql.fetch_all(query, tuple(args))
        return []

    async def get_app_logs(
        self,
        level: str | None = None,
        module: str | None = None,
        session_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query application logs with optional filters."""
        if self._mysql is not None and hasattr(self._mysql, "fetch_all"):
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
            order_dir = 'ASC' if since else 'DESC'
            query = f'SELECT * FROM app_logs WHERE {where} ORDER BY created_at {order_dir} LIMIT %s'
            args.append(limit)
            return await self._mysql.fetch_all(query, tuple(args))
        return []

    async def log_agent_trace(
        self,
        project_id: str,
        agent_name: str,
        event_type: str,
        token_count: int = 0,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record an agent event trace."""
        if self._mysql is not None and hasattr(self._mysql, "execute"):
            try:
                await self._mysql.execute(
                    '''INSERT INTO agent_traces (project_id, agent_name, event_type, token_count, details)
                       VALUES (%s, %s, %s, %s, %s)''',
                    (
                        project_id,
                        agent_name,
                        event_type,
                        token_count,
                        json.dumps(details, default=str) if details else None,
                    ),
                )
                return
            except Exception as e:
                logger.error('Failed to log agent trace: %s', e)
                logger.warning(
                    '[FALLBACK AGENT TRACE] project_id=%s agent=%s event=%s tokens=%d',
                    project_id, agent_name, event_type, token_count,
                )
                return

        logger.info("[AGENT TRACE] project_id=%s agent=%s event=%s tokens=%d", project_id, agent_name, event_type, token_count)

    async def get_agent_traces(
        self,
        project_id: str,
        agent_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query agent traces with optional filters."""
        if self._mysql is not None and hasattr(self._mysql, "fetch_all"):
            conditions: list[str] = ['project_id = %s']
            args: list[object] = [project_id]
            if agent_name:
                conditions.append('agent_name = %s')
                args.append(agent_name)
            if start_time:
                start_utc = start_time.astimezone(timezone.utc) if start_time.tzinfo is not None else start_time
                conditions.append('created_at >= %s')
                args.append(start_utc.strftime('%Y-%m-%d %H:%M:%S'))
            if end_time:
                end_utc = end_time.astimezone(timezone.utc) if end_time.tzinfo is not None else end_time
                conditions.append('created_at <= %s')
                args.append(end_utc.strftime('%Y-%m-%d %H:%M:%S'))
            where = ' AND '.join(conditions)
            query = f'SELECT * FROM agent_traces WHERE {where} ORDER BY created_at ASC LIMIT %s'
            args.append(limit)
            return await self._mysql.fetch_all(query, tuple(args))
        return []
