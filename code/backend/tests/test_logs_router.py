"""Tests for the logs and api-requests routing endpoints."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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

    mock_mysql = AsyncMock()
    mock_mysql.fetch_all.return_value = mock_logs

    from core.dependencies import get_mysql_service
    app.dependency_overrides[get_mysql_service] = lambda: mock_mysql
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

    # Verify that mysql_service was queried with the correct filters
    mock_mysql.fetch_all.assert_called_once()
    query = mock_mysql.fetch_all.call_args[0][0]
    args = mock_mysql.fetch_all.call_args[0][1]
    assert "UPPER(level) = %s" in query
    assert "module = %s" in query
    assert "session_id = %s" in query
    assert "created_at >= %s" in query
    assert "LIMIT %s" in query
    assert "INFO" in args
    assert "services.openalex_service" in args
    assert "session-1" in args
    assert "2026-05-30 17:00:00" in args
    assert 10 in args
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

    mock_mysql = AsyncMock()
    mock_mysql.fetch_all.return_value = mock_api_logs

    from core.dependencies import get_mysql_service
    app.dependency_overrides[get_mysql_service] = lambda: mock_mysql
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

    # Verify that mysql_service was queried with the correct filters
    mock_mysql.fetch_all.assert_called_once()
    query = mock_mysql.fetch_all.call_args[0][0]
    args = mock_mysql.fetch_all.call_args[0][1]
    assert "LOWER(service) = %s" in query
    assert "session_id = %s" in query
    assert "created_at >= %s" in query
    assert "LIMIT %s" in query
    assert "openalex" in args
    assert "session-1" in args

    assert "2026-05-30 17:00:00" in args
    assert 5 in args
    app.dependency_overrides.clear()


def test_logs_endpoints_service_unavailable() -> None:
    """Test endpoints return 503 if MySQL service is not initialized."""
    old_mysql = getattr(app.state, "mysql_service", None)
    if old_mysql is not None:
        del app.state.mysql_service

    try:
        client = TestClient(app)
        
        response1 = client.get("/api/logs")
        assert response1.status_code == 503
        assert "MySQL service not initialized" in response1.json()["detail"]

        response2 = client.get("/api/logs/api-requests")
        assert response2.status_code == 503
        assert "MySQL service not initialized" in response2.json()["detail"]
    finally:
        if old_mysql is not None:
            app.state.mysql_service = old_mysql

