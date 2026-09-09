"""Integration tests for Research Campaign REST and SSE endpoints matching campaign_api.yaml."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_neo4j_service


@pytest.fixture
def mock_neo4j() -> AsyncMock:
    """Mock Neo4j service for campaign router testing."""
    neo = AsyncMock()
    neo.execute_read.return_value = [
        {
            "campaign_id": "camp-123",
            "name": "Test Campaign",
            "topic": "Neural Networks",
            "entry_mode": "exploration",
            "status": "awaiting_input",
            "current_stage": 0,
            "token_budget": 500000,
            "tokens_used": 0,
            "total_turns": 0,
            "vts_ratio": 0.0,
            "created_at": "2026-09-09T00:00:00Z",
            "c": {
                "campaign_id": "camp-123",
                "status": "awaiting_input",
                "current_stage": 0,
            },
        }
    ]
    neo.execute_write.return_value = [
        {
            "campaign_id": "camp-123",
            "name": "Test Campaign",
            "topic": "Neural Networks",
            "entry_mode": "exploration",
            "status": "active",
            "current_stage": 0,
            "token_budget": 500000,
            "tokens_used": 0,
            "total_turns": 0,
            "vts_ratio": 0.0,
            "created_at": "2026-09-09T00:00:00Z",
        }
    ]
    return neo


@pytest.fixture
def client(mock_neo4j: AsyncMock) -> TestClient:
    """FastAPI TestClient with overridden get_neo4j_service dependency."""
    app.dependency_overrides[get_neo4j_service] = lambda: mock_neo4j
    yield TestClient(app)
    app.dependency_overrides.pop(get_neo4j_service, None)


def test_create_campaign_endpoint(client: TestClient) -> None:
    """Verify POST /api/campaigns creates campaign with 201 Created."""
    resp = client.post(
        "/api/campaigns",
        json={
            "topic": "Graph Neural Networks",
            "name": "GNN Review",
            "entry_mode": "exploration",
            "seed_dois": ["10.1145/3292500.3330964"],
            "research_questions": ["What is the expressive power of GNNs?"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["campaign_id"] == "camp-123"
    assert data["status"] == "active"


def test_list_campaigns_endpoint(client: TestClient) -> None:
    """Verify GET /api/campaigns returns campaign list with 200 OK."""
    resp = client.get("/api/campaigns?mode=exploration&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["campaign_id"] == "camp-123"


def test_get_campaign_detail_endpoint(client: TestClient) -> None:
    """Verify GET /api/campaigns/{id} returns campaign details."""
    resp = client.get("/api/campaigns/camp-123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == "camp-123"
    assert data["topic"] == "Neural Networks"


def test_get_campaign_detail_not_found(client: TestClient, mock_neo4j: AsyncMock) -> None:
    """Verify GET /api/campaigns/{id} returns 404 if not found."""
    mock_neo4j.execute_read.return_value = []
    resp = client.get("/api/campaigns/camp-nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_trigger_stage_execution_endpoint(client: TestClient) -> None:
    """Verify POST /api/campaigns/{id}/execute returns 202 Accepted."""
    resp = client.post(
        "/api/campaigns/camp-123/execute",
        json={"stage_index": 0, "force": True},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["campaign_id"] == "camp-123"
    assert data["status"] == "started"


def test_steer_campaign_endpoint(client: TestClient, mock_neo4j: AsyncMock) -> None:
    """Verify POST /api/campaigns/{id}/steering handles CONTINUE, EDIT_DIRECTIVE, FORCE_APPROVE, CONFIRM_ROLLBACK."""
    for action in ["CONTINUE", "EDIT_DIRECTIVE", "FORCE_APPROVE", "CONFIRM_ROLLBACK"]:
        resp = client.post(
            "/api/campaigns/camp-123/steering",
            json={
                "action": action,
                "stage_index": 1,
                "directives": f"Directive for {action}",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_id"] == "camp-123"

    # Verify rollback_stage_transaction was invoked for CONFIRM_ROLLBACK
    assert mock_neo4j.rollback_stage_transaction.called


def test_steer_campaign_not_awaiting_input(client: TestClient, mock_neo4j: AsyncMock) -> None:
    """Verify POST /api/campaigns/{id}/steering returns 409 Conflict if not in awaiting_input."""
    mock_neo4j.execute_read.return_value = [{"c": {"campaign_id": "camp-123", "status": "active"}}]
    resp = client.post(
        "/api/campaigns/camp-123/steering",
        json={"action": "CONTINUE", "stage_index": 1},
    )
    assert resp.status_code == 409
    assert "not awaiting input" in resp.json()["detail"].lower()



def test_stream_campaign_events_endpoint(client: TestClient) -> None:
    """Verify GET /api/campaigns/{id}/stream opens SSE text/event-stream."""
    resp = client.get("/api/campaigns/camp-123/stream")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "connected" in resp.text


def test_upload_paper_pdf_success(client: TestClient, mock_neo4j: AsyncMock) -> None:
    """Verify POST /api/campaigns/{id}/papers/{doi}/pdf successfully accepts and stores valid PDF."""
    mock_neo4j.execute_read.return_value = [{"c": {"campaign_id": "camp-123"}}, {"p": {"doi": "10.1234/test"}}]
    resp = client.post(
        "/api/campaigns/camp-123/papers/10.1234/test/pdf",
        files={"file": ("test.pdf", b"%PDF-1.5 test content", "application/pdf")},
        data={"is_authorized": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == "camp-123"
    assert data["doi"] == "10.1234/test"
    assert data["is_multimodal"] is True


def test_upload_paper_pdf_invalid_magic_bytes(client: TestClient, mock_neo4j: AsyncMock) -> None:
    """Verify POST /api/campaigns/{id}/papers/{doi}/pdf rejects invalid non-PDF file with 400."""
    resp = client.post(
        "/api/campaigns/camp-123/papers/10.1234/test/pdf",
        files={"file": ("fake.pdf", b"NOT_A_PDF", "application/pdf")},
        data={"is_authorized": "true"},
    )
    assert resp.status_code == 400
    assert "magic byte check failed" in resp.json()["detail"].lower()


def test_upload_paper_pdf_not_authorized(client: TestClient) -> None:
    """Verify POST /api/campaigns/{id}/papers/{doi}/pdf rejects unauthorized access with 400."""
    resp = client.post(
        "/api/campaigns/camp-123/papers/10.1234/test/pdf",
        files={"file": ("test.pdf", b"%PDF-1.5 test content", "application/pdf")},
        data={"is_authorized": "false"},
    )
    assert resp.status_code == 400
    assert "not authorized" in resp.json()["detail"].lower()

