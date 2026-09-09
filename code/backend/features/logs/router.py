"""Application and API crawl log endpoints for ALRS v2.

This router exposes two read-only log streams stored in the MySQL
``app_logs`` and ``api_logs`` tables.  Both endpoints support flexible
query-string filters (severity, module, service, date range, etc.)
powered by :class:`~core.logging.log_service.LogService`.

Data-translation patterns used in every endpoint:

*   **Timezone stamping** — MySQL's ``DATETIME`` columns are returned
    without timezone info by the ``aiomysql`` driver.  Before handing
    them to Pydantic we call ``datetime.replace(tzinfo=timezone.utc)``
    so the serialised JSON always carries an explicit UTC offset.

*   **JSON ``extra`` parsing** — The ``extra`` column in ``app_logs``
    stores arbitrary context as a JSON-encoded ``TEXT``.  The endpoint
    deserialises it with :func:`json.loads` and falls back to ``None``
    on parse failure to guarantee a clean ``dict | null`` contract.

Endpoints:
    GET /logs                → structured application log entries
    GET /logs/api-requests   → external API request / response logs
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from features.logs.models import (
    AppLogResponse,
    ApiLogResponse,
    AppLogQueryFilters,
    ApiLogQueryFilters,
    AgentTraceResponse,
    AgentTraceQueryFilters,
)
from core.logging.log_service import LogService
from core.logging.progress_service import ProgressEvent, ProgressService
from core.dependencies import get_log_service, get_progress_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("", response_model=List[AppLogResponse])
async def get_app_logs(
    filters: AppLogQueryFilters = Depends(),
    log_service: LogService = Depends(get_log_service),
) -> List[AppLogResponse]:
    """Retrieve structured application logs from the MySQL ``app_logs`` table.

    Supports optional query filtering by level, module, session_id,
    date range (``since``), and result cap (``limit``).

    Args:
        filters: Query-string filters injected via ``Depends()``.
        log_service: Injected log service (via FastAPI DI).

    Returns:
        A list of ``AppLogResponse`` entries ordered newest-first by
        the service layer.
    """
    logs = await log_service.get_app_logs(
        level=filters.level,
        module=filters.module,
        session_id=filters.session_id,
        since=filters.since,
        limit=filters.limit,
    )

    response_logs = []
    for log in logs:
        # The ``extra`` column is stored as a JSON-encoded TEXT in MySQL.
        # Attempt to deserialise it; fall back to None on any parse
        # error so the API always returns a clean dict | null contract.
        extra_val = log.get("extra")
        if isinstance(extra_val, str):
            try:
                extra_val = json.loads(extra_val)
            except Exception:
                extra_val = None

        response_logs.append(
            AppLogResponse(
                id=log["id"],
                session_id=log.get("session_id"),
                level=log["level"],
                module=log["module"],
                message=log["message"],
                # Only pass through successfully parsed dicts; reject
                # any other type (list, int, etc.) as non-conforming.
                extra=extra_val if isinstance(extra_val, dict) else None,
                # aiomysql returns naive datetimes; stamp UTC so the
                # serialised JSON always carries an explicit offset.
                created_at=log["created_at"].replace(tzinfo=timezone.utc) if isinstance(log["created_at"], datetime) and log["created_at"].tzinfo is None else log["created_at"],
            )
        )
    return response_logs


@router.get("/api-requests", response_model=List[ApiLogResponse])
async def get_api_logs(
    filters: ApiLogQueryFilters = Depends(),
    log_service: LogService = Depends(get_log_service),
) -> List[ApiLogResponse]:
    """Retrieve external API request/response crawl logs from the MySQL ``api_logs`` table.

    Supports optional query filtering by service name, session_id,
    date range (``since``), and result cap (``limit``).

    Args:
        filters: Query-string filters injected via ``Depends()``.
        log_service: Injected log service (via FastAPI DI).

    Returns:
        A list of ``ApiLogResponse`` entries ordered newest-first by
        the service layer.
    """
    logs = await log_service.get_api_logs(
        service=filters.service,
        session_id=filters.session_id,
        since=filters.since,
        limit=filters.limit,
    )

    return [
        ApiLogResponse(
            id=log["id"],
            session_id=log.get("session_id"),
            service=log["service"],
            method=log["method"],
            url=log["url"],
            status_code=log.get("status_code"),
            response_time_ms=log.get("response_time_ms"),
            payload_summary=log.get("payload_summary"),
            request_body=log.get("request_body"),
            response_body=log.get("response_body"),
            # Stamp naive datetimes with UTC — same pattern as get_app_logs.
            created_at=log["created_at"].replace(tzinfo=timezone.utc) if isinstance(log["created_at"], datetime) and log["created_at"].tzinfo is None else log["created_at"],
        )
        for log in logs
    ]


@router.get("/agent-traces", response_model=List[AgentTraceResponse])
async def get_agent_traces(
    filters: AgentTraceQueryFilters = Depends(),
    log_service: LogService = Depends(get_log_service),
) -> List[AgentTraceResponse]:
    """Retrieve multi-agent workflow execution logs and traces.

    Supports mandatory project filtering, optional agent name filtering,
    date range (``since`` and ``end_time``), and result cap (``limit``).

    Args:
        filters: Query-string filters injected via ``Depends()``.
        log_service: Injected log service (via FastAPI DI).

    Returns:
        A list of ``AgentTraceResponse`` entries ordered oldest-first by
        the service layer.
    """
    traces = await log_service.get_agent_traces(
        project_id=filters.project_id,
        agent_name=filters.agent_name,
        start_time=filters.since,
        end_time=filters.end_time,
        limit=filters.limit,
    )

    response_traces = []
    for trace in traces:
        # Details context column is stored as JSON-encoded TEXT in MySQL.
        # Deserialise it if it is a string; fall back to None on error.
        details_val = trace.get("details")
        if isinstance(details_val, str):
            try:
                details_val = json.loads(details_val)
            except Exception:
                details_val = None

        response_traces.append(
            AgentTraceResponse(
                id=trace["id"],
                project_id=trace["project_id"],
                agent_name=trace["agent_name"],
                event_type=trace["event_type"],
                token_count=trace.get("token_count") or 0,
                details=details_val if isinstance(details_val, dict) else None,
                # Stamp naive datetimes with UTC
                created_at=trace["created_at"].replace(tzinfo=timezone.utc) if isinstance(trace["created_at"], datetime) and trace["created_at"].tzinfo is None else trace["created_at"],
            )
        )
    return response_traces


@router.get("/progress/{project_id}/stream")
async def stream_project_progress(
    project_id: str,
    request: Request,
    include_history: bool = Query(default=True, description="Whether to yield past events before streaming live"),
    max_events: Optional[int] = Query(default=None, description="Optional maximum number of events to stream"),
) -> EventSourceResponse:
    """Stream real-time SSE progress events (thoughts, tool invocations, scores) for a project."""
    progress_service = getattr(request.app.state, "progress_service", None)
    if progress_service is None:
        from core.logging.progress_service import ProgressService
        progress_service = ProgressService()
        request.app.state.progress_service = progress_service

    return EventSourceResponse(
        progress_service.stream_events(
            project_id=project_id,
            include_history=include_history,
            max_events=max_events,
        )
    )


@router.get("/progress/{project_id}", response_model=List[ProgressEvent])
async def get_project_progress(
    project_id: str,
    request: Request,
    phase: Optional[str] = Query(default=None, description="Optional phase filter (planning, search, analysis, writing)"),
) -> List[ProgressEvent]:
    """Retrieve all in-memory progress events for a project."""
    progress_service = getattr(request.app.state, "progress_service", None)
    if progress_service is None:
        from core.logging.progress_service import ProgressService
        progress_service = ProgressService()
        request.app.state.progress_service = progress_service

    return await progress_service.get_events(project_id=project_id, phase=phase)


@router.get("/agent-traces/stream")
async def stream_agent_traces(
    request: Request,
    project_id: str = Query(..., description="Project UUID to stream traces for"),
    max_events: Optional[int] = Query(default=None, description="Optional maximum number of events to stream"),
) -> EventSourceResponse:
    """Stream real-time SSE events for agent traces in a project."""
    progress_service = getattr(request.app.state, "progress_service", None)
    if progress_service is None:
        from core.logging.progress_service import ProgressService
        progress_service = ProgressService()
        request.app.state.progress_service = progress_service

    return EventSourceResponse(
        progress_service.stream_events(
            project_id=project_id,
            include_history=True,
            max_events=max_events,
        )
    )


