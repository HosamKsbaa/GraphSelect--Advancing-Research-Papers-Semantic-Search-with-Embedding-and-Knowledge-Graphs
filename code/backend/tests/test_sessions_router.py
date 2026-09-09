"""Unit tests for features/sessions/router.py backed by Neo4j."""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from core.dependencies import get_neo4j_service
from main import app


@pytest.fixture
def mock_neo4j():
    mock = AsyncMock()
    mock.execute_read = AsyncMock(return_value=[])
    mock.execute_write = AsyncMock(return_value=[{"deleted_count": 1}])
    return mock


def test_list_sessions_empty(mock_neo4j):
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.get("/api/sessions")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 0
    assert data["sessions"] == []


def test_list_sessions_populated(mock_neo4j):
    mock_neo4j.execute_read.return_value = [
        {
            "c": {
                "campaign_id": "sess-123",
                "seed_doi": "10.1145/3292500.3330919",
                "research_questions": ["What is GNN?", "How does GNN scale?"],
                "similarity_threshold": 0.7,
                "max_depth": 2,
                "mode": "interactive",
                "status": "completed",
                "papers_discovered": 15,
                "papers_relevant": 8,
                "current_depth": 2,
                "created_at": "2026-09-08T20:00:00+00:00",
            }
        }
    ]
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.get("/api/sessions")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 1
    assert data["sessions"][0]["session_id"] == "sess-123"
    assert data["sessions"][0]["papers_discovered"] == 15


def test_get_session_found(mock_neo4j):
    mock_neo4j.execute_read.return_value = [
        {
            "c": {
                "campaign_id": "sess-123",
                "seed_doi": "10.1145/3292500.3330919",
                "research_questions": ["What is GNN?"],
                "similarity_threshold": 0.6,
                "max_depth": 2,
                "mode": "interactive",
                "status": "running",
                "papers_discovered": 5,
                "papers_relevant": 3,
                "current_depth": 1,
                "created_at": "2026-09-08T20:00:00+00:00",
            }
        }
    ]
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.get("/api/sessions/sess-123")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["session_id"] == "sess-123"


def test_get_session_not_found(mock_neo4j):
    mock_neo4j.execute_read.return_value = []
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.get("/api/sessions/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_session_success(mock_neo4j):
    mock_neo4j.execute_write.return_value = [{"deleted_count": 1}]
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.delete("/api/sessions/sess-123")
    assert response.status_code == status.HTTP_200_OK
    assert "deleted" in response.json()["message"]


def test_delete_session_not_found(mock_neo4j):
    mock_neo4j.execute_write.return_value = [{"deleted_count": 0}]
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    client = TestClient(app)
    response = client.delete("/api/sessions/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND
