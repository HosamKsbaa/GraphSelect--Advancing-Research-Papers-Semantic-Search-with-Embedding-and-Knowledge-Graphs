"""FastAPI logs router for ALRS v2 backend.

Exposes relational application and API crawl logs to the frontend with flexible query filters.
"""
from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.log_service import LogService
from dependencies import get_log_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


# --- Response Models ---

class AppLogResponse(BaseModel):
    """Pydantic model representing a structured application log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique log identifier")
    session_id: Optional[str] = Field(None, description="Associated session ID, if any")
    level: str = Field(..., description="Log level (e.g. INFO, ERROR, WARNING)")
    module: str = Field(..., description="Name of the module or service that produced the log")
    message: str = Field(..., description="The main log message")
    extra: Optional[Dict[str, Any]] = Field(None, description="Optional extra structured context data")
    created_at: datetime = Field(..., description="Timestamp of when the log was created")


class ApiLogResponse(BaseModel):
    """Pydantic model representing an external API request/response crawl log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique log identifier")
    session_id: Optional[str] = Field(None, description="Associated session ID, if any")
    service: str = Field(..., description="External service name (e.g. OpenAlex)")
    method: str = Field(..., description="HTTP method used (e.g. GET, POST)")
    url: str = Field(..., description="The target API URL")
    status_code: Optional[int] = Field(None, description="HTTP status code returned by the service")
    response_time_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    payload_summary: Optional[str] = Field(None, description="Summary or snippet of the request/response payload")
    created_at: datetime = Field(..., description="Timestamp of when the log was created")


# --- Query Parameter Models ---

class AppLogQueryFilters(BaseModel):
    """Query filters for application logs."""

    level: Optional[str] = Field(
        None,
        description="Filter logs by severity level (e.g. INFO, ERROR, WARNING)",
    )
    module: Optional[str] = Field(
        None,
        description="Filter logs by module or class name (e.g. services.openalex_service)",
    )
    session_id: Optional[str] = Field(
        None,
        description="Filter logs by the unique session ID",
    )
    since: Optional[datetime] = Field(
        None,
        description="Retrieve logs created on or after this ISO-8601 timestamp",
    )
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of log entries to return (default 100, max 1000)",
    )


class ApiLogQueryFilters(BaseModel):
    """Query filters for API crawl logs."""

    service: Optional[str] = Field(
        None,
        description="Filter logs by the external service name (e.g. OpenAlex)",
    )
    session_id: Optional[str] = Field(
        None,
        description="Filter logs by the unique session ID",
    )
    since: Optional[datetime] = Field(
        None,
        description="Retrieve logs created on or after this ISO-8601 timestamp",
    )
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of log entries to return (default 100, max 1000)",
    )


# --- Endpoints ---

@router.get("", response_model=List[AppLogResponse])
async def get_app_logs(
    filters: AppLogQueryFilters = Depends(),
    log_service: LogService = Depends(get_log_service),
) -> List[AppLogResponse]:
    """Retrieve structured application logs from the MySQL database.

    Supports optional query filtering by level, module, session_id, since, and limit.
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
        # Securely parse the extra field in case it is stored/returned as a JSON string
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
                extra=extra_val if isinstance(extra_val, dict) else None,
                created_at=log["created_at"],
            )
        )
    return response_logs


@router.get("/api-requests", response_model=List[ApiLogResponse])
async def get_api_logs(
    filters: ApiLogQueryFilters = Depends(),
    log_service: LogService = Depends(get_log_service),
) -> List[ApiLogResponse]:
    """Retrieve scholarly API request and response crawl logs from the MySQL database.

    Supports optional query filtering by service, session_id, since, and limit.
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
            created_at=log["created_at"],
        )
        for log in logs
    ]
