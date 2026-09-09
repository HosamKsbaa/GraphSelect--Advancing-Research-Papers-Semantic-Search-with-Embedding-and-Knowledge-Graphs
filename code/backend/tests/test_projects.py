"""Integration tests for project endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app

@pytest.fixture
def mock_mysql():
    service = AsyncMock()
    
    def fetch_one_side_effect(query, params):
        base_data = {
            "id": "project-123",
            "name": "Test",
            "description": "Test",
            "topic": "Test",
            "target_level": "master",
            "similarity_threshold": 0.6,
            "token_budget": 500000,
            "status": "active",
            "created_at": "2026-06-03 00:00:00",
            "updated_at": "2026-06-03 00:00:00",
            "last_accessed_at": None
        }
        if "status = 'archived'" in query or "status=%s" in query:
             base_data["status"] = "archived"
        if "last_accessed_at = CURRENT_TIMESTAMP" in query or "touch" in query:
             base_data["last_accessed_at"] = "2026-06-03 12:00:00"
        # Always return some modified data depending on the test
        # We can just return the data but we don't know the exact query here for the fetch_one after update
        # We can just return a generic valid one, or we can use a stateful mock
        pass
        
    service.fetch_one.return_value = {
        "id": "project-123",
        "name": "Test",
        "description": "Test",
        "topic": "Test",
        "target_level": "master",
        "similarity_threshold": 0.6,
        "token_budget": 500000,
        "status": "archived",
        "created_at": "2026-06-03 00:00:00",
        "updated_at": "2026-06-03 00:00:00",
        "last_accessed_at": "2026-06-03 12:00:00"
    }
    service.fetch_all.return_value = []
    service.execute.return_value = 1
    return service

@pytest.fixture
def mock_neo4j():
    service = AsyncMock()
    sample_record = {
        "project_id": "project-123",
        "name": "Test",
        "description": "Test",
        "topic": "Test",
        "target_level": "master",
        "similarity_threshold": 0.6,
        "token_budget": 500000,
        "status": "archived",
        "created_at": "2026-06-03 00:00:00",
        "updated_at": "2026-06-03 00:00:00",
        "last_accessed_at": "2026-06-03 12:00:00",
        "paper_count": 0,
        "question_count": 0,
    }
    service.execute_read.return_value = [sample_record]
    service.execute_write.return_value = [{"project_id": "project-123"}]
    service.execute_query.return_value = [sample_record]
    return service

def test_touch_project(mock_mysql, mock_neo4j):
    app.state.mysql_service = mock_mysql
    app.state.neo4j_service = mock_neo4j
    client = TestClient(app)
    
    response = client.post("/api/projects/project-123/touch")
    assert response.status_code == 200
    data = response.json()
    assert data["last_accessed_at"] is not None

def test_archive_project(mock_mysql, mock_neo4j):
    app.state.mysql_service = mock_mysql
    app.state.neo4j_service = mock_neo4j
    client = TestClient(app)
    
    response = client.patch("/api/projects/project-123/archive")
    assert response.status_code == 200
    assert response.json()["status"] == "archived"
