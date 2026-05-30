"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get('/api/health')
        assert response.status_code == 200
        data: dict = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'ALRS GraphSelect API'


class TestSearchEndpoint:
    def test_search_missing_api_key(self, client: TestClient) -> None:
        """Search should fail gracefully when API key is not set."""
        response = client.post(
            '/api/search',
            json={
                'seed_doi': '10.1038/s41586-020-2649-2',
                'research_questions': ['What is array programming?'],
            },
        )
        # Should return 400 Bad Request due to missing API key
        assert response.status_code == 400

    def test_search_validation_error(self, client: TestClient) -> None:
        """Search should reject invalid requests."""
        response = client.post(
            '/api/search',
            json={
                'seed_doi': '10.1038/test',
                'research_questions': [],  # Empty list not allowed (min_length=1)
            },
        )
        assert response.status_code == 422

    def test_search_missing_doi(self, client: TestClient) -> None:
        """Search should reject request without seed_doi."""
        response = client.post(
            '/api/search',
            json={
                'research_questions': ['Test question'],
            },
        )
        assert response.status_code == 422

    def test_search_threshold_validation(self, client: TestClient) -> None:
        """Similarity threshold must be between 0 and 1."""
        response = client.post(
            '/api/search',
            json={
                'seed_doi': '10.1038/test',
                'research_questions': ['Test'],
                'similarity_threshold': 1.5,  # Invalid
            },
        )
        assert response.status_code == 422

    def test_openapi_docs(self, client: TestClient) -> None:
        """OpenAPI docs should be accessible."""
        response = client.get('/openapi.json')
        assert response.status_code == 200
        data: dict = response.json()
        assert data['info']['title'] == 'ALRS GraphSelect API'
