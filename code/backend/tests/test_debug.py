import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from main import app
from core.dependencies import get_log_service, get_embedding_provider

def test_debug_test_embed_endpoint():
    # Setup mocks for logging and embedding providers
    mock_log = AsyncMock()
    mock_provider = AsyncMock()
    mock_provider.embed_document.return_value = [0.1] * 768

    app.dependency_overrides[get_log_service] = lambda: mock_log
    app.dependency_overrides[get_embedding_provider] = lambda: mock_provider

    try:
        client = TestClient(app)
        response = client.post("/api/debug/test-embed", json={"text": "Hello world"})
        
        assert response.status_code == 200, f"Unexpected status: {response.status_code}. Response: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("dimensions") == 768
        assert len(data.get("first_5_values", [])) == 5
    finally:
        app.dependency_overrides.clear()
