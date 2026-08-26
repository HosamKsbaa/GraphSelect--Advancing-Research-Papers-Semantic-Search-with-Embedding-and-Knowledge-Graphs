"""Integration tests for the research router REST endpoints."""
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_add_research_question_success() -> None:
    """Test adding a research question successfully."""
    # Mock Neo4j service
    mock_neo4j = AsyncMock()
    mock_neo4j.create_research_question.return_value = {
        "question_id": "q-123",
        "text": "What are the latest GNN architectures?",
    }
    app.state.neo4j_service = mock_neo4j

    # Mock embedding provider
    mock_provider_instance = AsyncMock()
    mock_provider_instance.embed_query.return_value = [0.1] * 768

    with patch(
        "features.embedding.providers.gemini_provider.GeminiEmbeddingProvider",
        return_value=mock_provider_instance,
    ):
        client = TestClient(app)
        response = client.post(
            "/api/research/project-123/questions",
            json={"question_text": "What are the latest GNN architectures?"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "created"
        assert data["question_id"] == "q-123"
        assert data["text"] == "What are the latest GNN architectures?"
        assert data["project_id"] == "project-123"

        mock_neo4j.create_research_question.assert_called_once_with(
            question_id=ANY,
            text="What are the latest GNN architectures?",
            embedding=[0.1] * 768,
            project_id="project-123",
        )
        mock_provider_instance.embed_query.assert_called_once()


def test_list_research_questions_success() -> None:
    """Test listing research questions successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = [
        {"question_id": "q-1", "text": "Question 1"},
        {"question_id": "q-2", "text": "Question 2"},
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/research/project-123/questions")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 2
    assert len(data["questions"]) == 2
    assert data["questions"][0]["question_id"] == "q-1"
    assert data["questions"][1]["text"] == "Question 2"

    mock_neo4j.get_research_questions.assert_called_once_with("project-123")


def test_get_top_authors_success() -> None:
    """Test getting top authors successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [
        {"name": "Alice Smith", "openalex_id": "A111", "paper_count": 5},
        {"name": "Bob Jones", "openalex_id": "A222", "paper_count": 3},
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/research/project-123/top-authors?limit=5")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 2
    assert len(data["authors"]) == 2
    assert data["authors"][0]["name"] == "Alice Smith"
    assert data["authors"][0]["paper_count"] == 5

    mock_neo4j.execute_read.assert_called_once()
    assert "limit" in mock_neo4j.execute_read.call_args[0][1]


def test_get_top_venues_success() -> None:
    """Test getting top venues successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [
        {"name": "Nature GNN", "openalex_id": "V999", "paper_count": 12},
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/research/project-123/top-venues?limit=3")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 1
    assert len(data["venues"]) == 1
    assert data["venues"][0]["name"] == "Nature GNN"
    assert data["venues"][0]["paper_count"] == 12

    mock_neo4j.execute_read.assert_called_once()


def test_search_by_author_success() -> None:
    """Test searching OpenAlex by author."""
    mock_openalex_instance = AsyncMock()
    mock_openalex_instance._request.return_value = {
        "results": [
            {
                "doi": "https://doi.org/10.1234/test.doi",
                "title": "A GNN study",
                "publication_year": 2024,
                "cited_by_count": 15,
                "authorships": [
                    {"author": {"display_name": "Alice Smith"}},
                    {"author": {"display_name": "Bob Jones"}},
                ],
            }
        ]
    }

    with patch(
        "core.clients.openalex_client.OpenAlexService",
        return_value=mock_openalex_instance,
    ):
        client = TestClient(app)
        response = client.get("/api/research/search/author?name=Alice&max_results=5")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_returned"] == 1
        assert len(data["papers"]) == 1
        assert data["papers"][0]["doi"] == "10.1234/test.doi"
        assert data["papers"][0]["title"] == "A GNN study"
        assert data["papers"][0]["year"] == 2024
        assert data["papers"][0]["cited_by_count"] == 15
        assert data["papers"][0]["authors"] == ["Alice Smith", "Bob Jones"]

        mock_openalex_instance._request.assert_called_once()
        mock_openalex_instance.close.assert_called_once()


def test_search_by_venue_success() -> None:
    """Test searching OpenAlex by venue."""
    mock_openalex_instance = AsyncMock()
    mock_openalex_instance._request.return_value = {
        "results": [
            {
                "doi": "https://doi.org/10.5678/venue.doi",
                "title": "Venue Paper",
                "publication_year": 2023,
                "cited_by_count": 42,
                "authorships": [
                    {"author": {"display_name": "Charlie Brown"}},
                ],
            }
        ]
    }

    with patch(
        "core.clients.openalex_client.OpenAlexService",
        return_value=mock_openalex_instance,
    ):
        client = TestClient(app)
        response = client.get("/api/research/search/venue?name=Nature&max_results=2")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_returned"] == 1
        assert len(data["papers"]) == 1
        assert data["papers"][0]["doi"] == "10.5678/venue.doi"
        assert data["papers"][0]["title"] == "Venue Paper"
        assert data["papers"][0]["year"] == 2023
        assert data["papers"][0]["cited_by_count"] == 42
        assert data["papers"][0]["authors"] == ["Charlie Brown"]

        mock_openalex_instance._request.assert_called_once()
        mock_openalex_instance.close.assert_called_once()


def test_decompose_query_endpoint_success() -> None:
    """Test decomposing a high-level research topic into sub-questions."""
    mock_neo4j = AsyncMock()
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    from core.llm.models import CompletionResponse, TokenUsage
    mock_llm_instance.complete.return_value = CompletionResponse(
        text='{"sub_questions": ["What GNN architectures scale to large graphs?", "How do GNNs compare to Graph Transformers?", "What are the expressive power limits of message passing?", "What benchmarks evaluate graph embeddings?"]}',
        token_usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
    )

    with patch("core.llm.service.LLMService", return_value=mock_llm_instance):
        client = TestClient(app)
        response = client.post(
            "/api/research/project-123/decompose-query",
            json={
                "topic": "Graph Neural Networks and Graph Transformers",
                "num_questions": 4,
                "auto_save": False,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["project_id"] == "project-123"
        assert data["topic"] == "Graph Neural Networks and Graph Transformers"
        assert data["total"] == 4
        assert len(data["sub_questions"]) == 4
        assert "What GNN architectures scale to large graphs?" in data["sub_questions"]


def test_decompose_query_endpoint_auto_save() -> None:
    """Test decomposing a research topic and auto-saving sub-questions."""
    mock_neo4j = AsyncMock()
    mock_neo4j.create_research_question.side_effect = [
        {"question_id": f"q-{i}", "text": f"Sub-Q {i}?"} for i in range(1, 5)
    ]
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    from core.llm.models import CompletionResponse, TokenUsage
    mock_llm_instance.complete.return_value = CompletionResponse(
        text='{"sub_questions": ["Sub-Q 1?", "Sub-Q 2?", "Sub-Q 3?", "Sub-Q 4?"]}',
        token_usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
    )

    mock_provider = AsyncMock()
    mock_provider.embed_query.return_value = [0.05] * 768

    with patch("core.llm.service.LLMService", return_value=mock_llm_instance), patch(
        "features.embedding.providers.gemini_provider.GeminiEmbeddingProvider",
        return_value=mock_provider,
    ):
        client = TestClient(app)
        response = client.post(
            "/api/research/project-123/decompose-query",
            json={
                "topic": "Alzheimers Disease Multimodal Deep Learning",
                "num_questions": 4,
                "auto_save": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 4
        assert len(data["saved_questions"]) == 4
        assert mock_neo4j.create_research_question.call_count == 4

