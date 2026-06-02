"""Integration tests for the analysis router REST endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_compute_paper_similarity_success() -> None:
    """Test computing similarity between a paper and project research questions."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = [{"question_id": "q-1", "text": "Question 1"}]
    mock_neo4j.has_embedding.return_value = True
    mock_neo4j.compute_similarities.return_value = [
        {"doi": "10.1234/test", "question": "Question 1", "score": 0.85}
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/analysis/project-123/similarity/10.1234/test")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["doi"] == "10.1234/test"
    assert len(data["scores"]) == 1
    assert data["scores"][0]["question"] == "Question 1"
    assert data["scores"][0]["score"] == 0.85
    assert data["avg_score"] == 0.85

    mock_neo4j.get_research_questions.assert_called_once_with("project-123")
    mock_neo4j.has_embedding.assert_called_once_with("10.1234/test")
    mock_neo4j.compute_similarities.assert_called_once()


def test_get_citation_stats_success() -> None:
    """Test retrieving citation statistics for a project."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [
        {"doi": "10.1234/1", "cited_by_count": 10},
        {"doi": "10.1234/2", "cited_by_count": 20},
    ]
    mock_neo4j.get_research_questions.return_value = [{"question_id": "q-1", "text": "Question 1"}]
    mock_neo4j.compute_similarities.return_value = [
        {"doi": "10.1234/1", "question": "Question 1", "score": 0.7},
        {"doi": "10.1234/2", "question": "Question 1", "score": 0.9},
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/analysis/project-123/citation-stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_papers"] == 2
    assert data["total_citations"] == 30
    assert data["avg_citations"] == 15.0
    assert len(data["question_coverage"]) == 1
    assert data["question_coverage"][0]["question"] == "Question 1"
    assert data["question_coverage"][0]["avg_similarity"] == 0.8
    assert data["question_coverage"][0]["paper_count"] == 2


def test_analyze_coverage_success() -> None:
    """Test coverage analysis of research questions."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = [
        {"question_id": "q-1", "text": "Question 1"},
        {"question_id": "q-2", "text": "Question 2"},
    ]
    mock_neo4j.get_project_papers.return_value = [
        {"doi": "10.1234/1"},
    ]
    mock_neo4j.compute_similarities.return_value = [
        {"doi": "10.1234/1", "question": "Question 1", "score": 0.75},
        {"doi": "10.1234/1", "question": "Question 2", "score": 0.45},
    ]
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.get("/api/analysis/project-123/coverage?threshold=0.6")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["overall_coverage"] == 0.5
    assert len(data["covered_questions"]) == 1
    assert data["covered_questions"][0]["question"] == "Question 1"
    assert len(data["gap_questions"]) == 1
    assert data["gap_questions"][0]["question"] == "Question 2"
    assert data["recommendation"] is not None


def test_suggest_gap_queries_success() -> None:
    """Test suggesting search queries using mock LLM service."""
    mock_llm_instance = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = '["query one", "query two", "query three"]'
    mock_llm_instance.complete.return_value = mock_response

    with patch(
        "core.llm.service.LLMService",
        return_value=mock_llm_instance,
    ):
        client = TestClient(app)
        response = client.post(
            "/api/analysis/project-123/gap-queries",
            json={"gap_question": "What is the meaning of life?", "max_queries": 2},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["gap_question"] == "What is the meaning of life?"
        assert data["suggested_queries"] == ["query one", "query two"]

        mock_llm_instance.complete.assert_called_once()


def test_rank_papers_success() -> None:
    """Test ranking papers based on similarity and PageRank hybrid scoring."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [
        {"doi": "10.1234/1", "title": "Paper 1", "year": 2020, "cited_by_count": 5},
        {"doi": "10.1234/2", "title": "Paper 2", "year": 2021, "cited_by_count": 12},
    ]
    mock_neo4j.compute_similarities.return_value = [
        {"doi": "10.1234/1", "score": 0.8},
        {"doi": "10.1234/2", "score": 0.6},
    ]
    mock_neo4j.compute_pagerank.return_value = {
        "10.1234/1": 0.2,
        "10.1234/2": 0.9,
    }
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    # weights: sim = 0.5, pagerank = 0.5
    # paper 1: 0.5 * 0.8 + 0.5 * 0.2 = 0.5
    # paper 2: 0.5 * 0.6 + 0.5 * 0.9 = 0.75
    # So Paper 2 should rank first!
    response = client.get("/api/analysis/project-123/ranked-papers?similarity_weight=0.5&pagerank_weight=0.5")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 2
    assert data["weights"]["similarity"] == 0.5
    assert data["weights"]["pagerank"] == 0.5
    assert len(data["ranked_papers"]) == 2
    assert data["ranked_papers"][0]["doi"] == "10.1234/2"
    assert data["ranked_papers"][0]["hybrid_score"] == 0.75
    assert data["ranked_papers"][1]["doi"] == "10.1234/1"
    assert data["ranked_papers"][1]["hybrid_score"] == 0.5
