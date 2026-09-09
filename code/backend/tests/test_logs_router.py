"""Tests for the logs and api-requests routing endpoints."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.dependencies import get_log_service
from core.logging.log_service import LogService
from main import app


def test_get_app_logs_success() -> None:
    """Test retrieving application logs with valid query filters."""
    mock_logs = [
        {
            "id": 1,
            "session_id": "session-1",
            "level": "INFO",
            "module": "services.openalex_service",
            "message": "Fetched seed paper details",
            "extra": '{"doi": "10.1234/seed"}',
            "created_at": datetime(2026, 5, 30, 18, 0, 0),
        },
        {
            "id": 2,
            "session_id": "session-1",
            "level": "ERROR",
            "module": "services.openalex_service",
            "message": "Connection timeout",
            "extra": None,
            "created_at": datetime(2026, 5, 30, 18, 1, 0),
        }
    ]

    mock_log_svc = AsyncMock(spec=LogService)
    mock_log_svc.get_app_logs = AsyncMock(return_value=mock_logs)

    app.dependency_overrides[get_log_service] = lambda: mock_log_svc
    client = TestClient(app)
    response = client.get(
        "/api/logs",
        params={
            "level": "info",
            "module": "services.openalex_service",
            "session_id": "session-1",
            "since": "2026-05-30T17:00:00",
            "limit": 10
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[0]["level"] == "INFO"
    assert data[0]["extra"] == {"doi": "10.1234/seed"}
    assert data[1]["id"] == 2
    assert data[1]["extra"] is None

    mock_log_svc.get_app_logs.assert_called_once()
    app.dependency_overrides.clear()


def test_get_api_logs_success() -> None:
    """Test retrieving API crawl logs with query filters."""
    mock_api_logs = [
        {
            "id": 101,
            "session_id": "session-1",
            "service": "OpenAlex",
            "method": "GET",
            "url": "https://api.openalex.org/works/10.1234/seed",
            "status_code": 200,
            "response_time_ms": 120,
            "payload_summary": "Fetched successfully",
            "created_at": datetime(2026, 5, 30, 18, 0, 0),
        }
    ]

    mock_log_svc = AsyncMock(spec=LogService)
    mock_log_svc.get_api_logs = AsyncMock(return_value=mock_api_logs)

    app.dependency_overrides[get_log_service] = lambda: mock_log_svc
    client = TestClient(app)
    response = client.get(
        "/api/logs/api-requests",
        params={
            "service": "OpenAlex",
            "session_id": "session-1",
            "since": "2026-05-30T17:00:00",
            "limit": 5
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 101
    assert data[0]["service"] == "OpenAlex"
    assert data[0]["status_code"] == 200
    assert data[0]["response_time_ms"] == 120

    mock_log_svc.get_api_logs.assert_called_once()
    app.dependency_overrides.clear()


def test_get_agent_traces_success() -> None:
    """Test retrieving agent traces with valid query filters."""
    mock_traces = [
        {
            "id": 1,
            "project_id": "project-123",
            "agent_name": "planner",
            "event_type": "llm_call",
            "token_count": 2500,
            "details": '{"prompt": "design outline", "tokens": 2500}',
            "created_at": datetime(2026, 5, 30, 18, 0, 0),
        }
    ]

    mock_log_svc = AsyncMock(spec=LogService)
    mock_log_svc.get_agent_traces = AsyncMock(return_value=mock_traces)

    app.dependency_overrides[get_log_service] = lambda: mock_log_svc
    client = TestClient(app)
    response = client.get(
        "/api/logs/agent-traces",
        params={
            "project_id": "project-123",
            "agent_name": "planner",
            "since": "2026-05-30T17:00:00",
            "end_time": "2026-05-30T19:00:00",
            "limit": 50,
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["project_id"] == "project-123"
    assert data[0]["agent_name"] == "planner"
    assert data[0]["token_count"] == 2500
    assert data[0]["details"] == {"prompt": "design outline", "tokens": 2500}

    mock_log_svc.get_agent_traces.assert_called_once()
    app.dependency_overrides.clear()


def test_get_project_progress_events() -> None:
    """Test retrieving in-memory progress events for a project."""
    from core.logging.progress_service import ProgressEvent, ProgressService

    progress_svc = ProgressService()
    app.state.progress_service = progress_svc

    import asyncio
    asyncio.run(
        progress_svc.emit(
            "project-123",
            ProgressEvent(
                phase="writing",
                status="in_progress",
                message="Drafting section 1",
                details={"section": "Introduction"},
            ),
        )
    )

    client = TestClient(app)
    response = client.get("/api/logs/progress/project-123")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["phase"] == "writing"
    assert data[0]["status"] == "in_progress"
    assert data[0]["message"] == "Drafting section 1"
    assert data[0]["details"] == {"section": "Introduction"}


def test_stream_project_progress_sse() -> None:
    """Test streaming real-time SSE progress events for a project."""
    import asyncio
    from core.logging.progress_service import ProgressEvent, ProgressService

    progress_svc = ProgressService()
    app.state.progress_service = progress_svc

    asyncio.run(
        progress_svc.emit(
            "project-stream-test",
            ProgressEvent(
                phase="analysis",
                status="completed",
                message="Evidence synthesis completed",
                details={"papers_count": 5},
            ),
        )
    )

    client = TestClient(app)
    with client.stream("GET", "/api/logs/progress/project-stream-test/stream?include_history=true&max_events=1") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        lines = [line for line in response.iter_lines() if line]
        full_stream_text = "\n".join(lines)
        assert "progress" in full_stream_text
        assert "Evidence synthesis completed" in full_stream_text


def test_stream_agent_traces_sse() -> None:
    """Test streaming agent traces endpoint via SSE."""
    import asyncio
    from core.logging.progress_service import ProgressEvent, ProgressService

    progress_svc = ProgressService()
    app.state.progress_service = progress_svc

    asyncio.run(
        progress_svc.emit(
            "project-trace-test",
            ProgressEvent(
                phase="planning",
                status="in_progress",
                message="PlannerAgent outline step",
                details={"step": 1},
            ),
        )
    )

    client = TestClient(app)
    with client.stream("GET", "/api/logs/agent-traces/stream?project_id=project-trace-test&max_events=1") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        lines = [line for line in response.iter_lines() if line]
        full_stream_text = "\n".join(lines)
        assert "PlannerAgent outline step" in full_stream_text


@pytest.mark.asyncio
async def test_progress_service_live_subscription_broadcast() -> None:
    """Test live ProgressEvent broadcast across active subscriber queues."""
    import asyncio
    from core.logging.progress_service import ProgressEvent, ProgressService

    svc = ProgressService()
    queue = svc.subscribe("live-proj-1")

    ev = ProgressEvent(
        phase="writing",
        status="in_progress",
        message="Reviewer score 5/5",
        details={"score": 5},
    )
    await svc.emit("live-proj-1", ev)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.phase == "writing"
    assert received.message == "Reviewer score 5/5"

    svc.unsubscribe("live-proj-1", queue)
