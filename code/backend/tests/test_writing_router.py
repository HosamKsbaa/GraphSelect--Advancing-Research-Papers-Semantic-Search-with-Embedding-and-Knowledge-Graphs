"""Integration tests for the writing router REST endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_get_paper_abstracts_success() -> None:
    """Test retrieving paper abstracts successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi.return_value = {
        "doi": "10.1234/test",
        "title": "GNN Review",
        "abstract": "We review Graph Neural Networks...",
        "year": 2021,
        "source": "openalex",
    }
    app.state.neo4j_service = mock_neo4j

    client = TestClient(app)
    response = client.post(
        "/api/writing/project-123/abstracts",
        json={"dois": ["10.1234/test"]},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "papers" in data
    assert len(data["papers"]) == 1
    assert data["papers"][0]["doi"] == "10.1234/test"
    assert data["papers"][0]["title"] == "GNN Review"
    assert data["papers"][0]["abstract"] == "We review Graph Neural Networks..."

    mock_neo4j.get_paper_by_doi.assert_called_once_with("10.1234/test")


def test_draft_section_success(tmp_path: Path) -> None:
    """Test drafting a section successfully using mock LLM."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi.return_value = {
        "doi": "10.1234/test",
        "title": "GNN Review",
        "abstract": "We review Graph Neural Networks...",
        "year": 2021,
        "source": "openalex",
    }
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "This is a drafted section text citing (10.1234/test)."
    mock_response.usage.total_tokens = 150
    mock_llm_instance.complete.return_value = mock_response
    app.state.llm_service = mock_llm_instance

    from config import Settings
    mock_settings = MagicMock(spec=Settings)
    mock_settings.projects_dir = str(tmp_path)

    with patch("config.get_settings", return_value=mock_settings):
        client = TestClient(app)
        response = client.post(
            "/api/writing/project-123/draft",
            json={
                "section_title": "Introduction to GNNs",
                "section_description": "Scope of GNNs.",
                "paper_dois": ["10.1234/test"],
                "target_level": "master",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["section_title"] == "Introduction to GNNs"
        assert data["markdown"] == "This is a drafted section text citing (10.1234/test)."
        assert data["word_count"] > 0
        assert data["cited_dois"] == ["10.1234/test"]
        assert "saved_path" in data

        # Verify draft was written to disk
        saved_file = Path(data["saved_path"])
        assert saved_file.exists()
        assert saved_file.read_text(encoding="utf-8") == data["markdown"]


def test_review_section_success() -> None:
    """Test reviewing a drafted section successfully using mock LLM."""
    mock_llm_instance = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "approved": True,
        "scores": {
            "citation_coverage": 5,
            "coherence": 5,
            "synthesis": 4,
            "academic_tone": 4,
            "completeness": 5,
        },
        "feedback": ["Great work!"],
        "missing_citations": [],
    })
    mock_response.usage.total_tokens = 90
    mock_llm_instance.complete.return_value = mock_response
    app.state.llm_service = mock_llm_instance

    client = TestClient(app)
    response = client.post(
        "/api/writing/project-123/review",
        json={
            "section_title": "Introduction to GNNs",
            "draft_text": "This is a drafted section text citing (10.1234/test).",
            "paper_dois": ["10.1234/test"],
            "target_level": "master",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["approved"] is True
    assert data["scores"]["coherence"] == 5
    assert data["feedback"] == ["Great work!"]
    assert data["missing_citations"] == []
