"""Pydantic request/response and query-filter models for the logs feature."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Response Models ──────────────────────────────────────────────────


class AppLogResponse(BaseModel):
    """Pydantic model representing a structured application log entry.

    Maps 1-to-1 with a row in the ``app_logs`` MySQL table.
    The ``extra`` field is nullable because not every log event carries
    additional context data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique log identifier")
    session_id: Optional[str] = Field(None, description="Associated session ID, if any")
    level: str = Field(..., description="Log level (e.g. INFO, ERROR, WARNING)")
    module: str = Field(..., description="Name of the module or service that produced the log")
    message: str = Field(..., description="The main log message")
    extra: Optional[Dict[str, Any]] = Field(None, description="Optional extra structured context data")
    created_at: datetime = Field(..., description="Timestamp of when the log was created")


class ApiLogResponse(BaseModel):
    """Pydantic model representing an external API request/response crawl log entry.

    Maps 1-to-1 with a row in the ``api_logs`` MySQL table.  Both the
    request and response bodies are stored as nullable ``TEXT`` columns
    to allow full payload inspection during debugging.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique log identifier")
    session_id: Optional[str] = Field(None, description="Associated session ID, if any")
    service: str = Field(..., description="External service name (e.g. OpenAlex)")
    method: str = Field(..., description="HTTP method used (e.g. GET, POST)")
    url: str = Field(..., description="The target API URL")
    status_code: Optional[int] = Field(None, description="HTTP status code returned by the service")
    response_time_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    payload_summary: Optional[str] = Field(None, description="Summary or snippet of the request/response payload")
    request_body: Optional[str] = Field(None, description="The full JSON request payload sent")
    response_body: Optional[str] = Field(None, description="The full JSON response payload received")
    created_at: datetime = Field(..., description="Timestamp of when the log was created")


# ── Query Parameter Models ───────────────────────────────────────────


class AppLogQueryFilters(BaseModel):
    """Query-string filters for the ``GET /logs`` endpoint.

    FastAPI injects each field from the corresponding query parameter
    via ``Depends()``.  All filters are optional; omitting them returns
    the most recent *limit* entries unfiltered.
    """

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
    """Query-string filters for the ``GET /logs/api-requests`` endpoint.

    Similar to :class:`AppLogQueryFilters` but scoped to the fields
    relevant for external API crawl logs (``service`` instead of
    ``level`` / ``module``).
    """

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


class AgentTraceResponse(BaseModel):
    """Pydantic model representing an agent event trace entry.

    Maps 1-to-1 with a row in the ``agent_traces`` MySQL table.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique trace identifier")
    project_id: str = Field(..., description="Associated project UUID")
    agent_name: str = Field(..., description="Name of the agent (e.g. planner, search)")
    event_type: str = Field(..., description="Type of trace event (e.g. start, end, tool_call, llm_call)")
    token_count: int = Field(0, description="Token consumption for the event")
    details: Optional[Dict[str, Any]] = Field(None, description="Optional structured details context data")
    created_at: datetime = Field(..., description="Timestamp of when the trace was created")


class AgentTraceQueryFilters(BaseModel):
    """Query-string filters for the ``GET /logs/agent-traces`` endpoint."""

    project_id: str = Field(..., description="Filter traces by project ID (required)")
    agent_name: Optional[str] = Field(None, description="Filter traces by agent name")
    since: Optional[datetime] = Field(None, description="Filter traces created on or after this ISO-8601 timestamp")
    end_time: Optional[datetime] = Field(None, description="Filter traces created on or before this ISO-8601 timestamp")
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of trace entries to return (default 100, max 1000)",
    )

