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


def test_synthesize_evidence_endpoint_success() -> None:
    """Test synthesizing literature evidence across all project papers."""
    import json
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [
        {"doi": "10.1234/paper1", "title": "Graph Attention Networks", "year": 2021, "abstract": "We present GAT..."}
    ]
    mock_neo4j.get_research_questions.return_value = [
        {"question_id": "q-1", "text": "How do attention mechanisms scale on graphs?"}
    ]
    mock_neo4j.get_paper_by_doi.return_value = {
        "doi": "10.1234/paper1",
        "title": "Graph Attention Networks",
        "year": 2021,
        "abstract": "We present GAT...",
    }
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    # Mock finding extraction response followed by matrix generation response
    extract_resp = MagicMock()
    extract_resp.text = json.dumps({
        "methodology": "Multi-head self-attention on graph neighborhoods",
        "key_findings": ["Outperforms standard GCN on citation benchmarks"],
        "datasets_or_benchmarks": ["Cora", "Citeseer", "Pubmed"],
        "limitations": ["Quadratic memory in dense graphs"],
    })
    extract_resp.usage.total_tokens = 120

    matrix_resp = MagicMock()
    matrix_resp.text = json.dumps({
        "dimensions": [
            {
                "dimension_name": "Scalability",
                "findings_by_doi": {"10.1234/paper1": "Moderate scalability"},
                "consensus": "Attention scales with edge count",
                "divergence": "Memory overhead varies with heads",
            }
        ],
        "synthesis_narrative": "Literature indicates strong empirical gains for graph attention mechanisms.",
    })
    matrix_resp.usage.total_tokens = 250

    mock_llm_instance.complete.side_effect = [extract_resp, matrix_resp]
    app.state.llm_service = mock_llm_instance

    client = TestClient(app)
    response = client.post("/api/analysis/project-123/synthesize")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["project_id"] == "project-123"
    assert data["paper_count"] == 1
    assert len(data["findings"]) == 1
    assert data["findings"][0]["doi"] == "10.1234/paper1"
    assert data["findings"][0]["methodology"] == "Multi-head self-attention on graph neighborhoods"
    assert len(data["comparison_matrix"]["dimensions"]) == 1
    assert "Scalability" in data["comparison_matrix"]["dimensions"][0]["dimension_name"]
    assert "Dimension" in data["markdown_table"]
    assert len(data["synthesis_narrative"]) > 0


def test_synthesize_evidence_endpoint_with_custom_dois_and_questions() -> None:
    """Test synthesizing literature evidence with specific custom DOIs and research questions."""
    import json
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi.return_value = {
        "doi": "10.1234/custom1",
        "title": "Custom Sparse GNN",
        "year": 2023,
        "abstract": "We evaluate sparse graph operations...",
    }
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    extract_resp = MagicMock()
    extract_resp.text = json.dumps({
        "methodology": "Sparse tensor factorization",
        "key_findings": ["Reduces memory footprint by 4x"],
        "datasets_or_benchmarks": ["OGB-Arxiv"],
        "limitations": ["Limited to static graphs"],
    })
    extract_resp.usage.total_tokens = 100

    matrix_resp = MagicMock()
    matrix_resp.text = json.dumps({
        "dimensions": [
            {
                "dimension_name": "Efficiency",
                "findings_by_doi": {"10.1234/custom1": "4x memory reduction"},
                "consensus": "Sparsity improves memory efficiency",
                "divergence": "Static vs dynamic graph trade-offs",
            }
        ],
        "synthesis_narrative": "Sparse GNNs achieve superior memory efficiency on large graphs.",
    })
    matrix_resp.usage.total_tokens = 200

    mock_llm_instance.complete.side_effect = [extract_resp, matrix_resp]
    app.state.llm_service = mock_llm_instance

    client = TestClient(app)
    response = client.post(
        "/api/analysis/project-123/synthesize",
        json={
            "dois": ["10.1234/custom1"],
            "research_questions": ["What are the memory bottlenecks in GNN scaling?"],
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["project_id"] == "project-123"
    assert data["paper_count"] == 1
    assert data["findings"][0]["doi"] == "10.1234/custom1"
    assert data["comparison_matrix"]["dimensions"][0]["dimension_name"] == "Efficiency"


def test_synthesize_evidence_endpoint_service_unavailable() -> None:
    """Test synthesize endpoint returns 503 when Neo4j is not available."""
    old_neo4j = getattr(app.state, "neo4j_service", None)
    app.state.neo4j_service = None
    try:
        client = TestClient(app)
        response = client.post("/api/analysis/project-123/synthesize")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        app.state.neo4j_service = old_neo4j

