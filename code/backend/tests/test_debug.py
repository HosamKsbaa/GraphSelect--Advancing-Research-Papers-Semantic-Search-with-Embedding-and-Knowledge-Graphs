import pytest
from fastapi.testclient import TestClient
from main import app
from config import get_settings

client = TestClient(app)

def test_debug_test_embed_endpoint():
    # Use TestClient as a context manager to trigger startup events (initializes mysql_service)
    with TestClient(app) as client:
        # Attempt to call the debug embed endpoint
        # This might fail with 400 if the API key is placeholder, but should not 500
        response = client.post("/api/debug/test-embed", json={"text": "Hello world"})
        
        # Assert that the endpoint returns 200 OK and successfully completes the embedding
        assert response.status_code == 200, f"Unexpected status code: {response.status_code}. Response: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Embedding failed with error: {data.get('error')}"
