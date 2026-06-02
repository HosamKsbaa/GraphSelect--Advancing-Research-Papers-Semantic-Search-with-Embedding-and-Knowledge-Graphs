"""Integration tests for the planning router REST endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_get_project_summary_success(tmp_path: Path) -> None:
    """Test getting a project summary successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [{"doi": "10.1234/1"}, {"doi": "10.1234/2"}]
    mock_neo4j.get_research_questions.return_value = [
        {"question_id": "q-1", "text": "Question One"},
        {"question_id": "q-2", "text": "Question Two"},
    ]
    mock_neo4j.execute_read.return_value = [{"gap_count": 1}]
    app.state.neo4j_service = mock_neo4j

    # Create dummy outline on disk to verify file check logic
    project_dir = tmp_path / "project-123"
    outlines_dir = project_dir / "outlines"
    outlines_dir.mkdir(parents=True)
    (outlines_dir / "outline.json").write_text("{}")

    # Mock settings to use tmp_path as projects_dir
    from config import Settings
    mock_settings = MagicMock(spec=Settings)
    mock_settings.projects_dir = str(tmp_path)

    with patch("config.get_settings", return_value=mock_settings):
        client = TestClient(app)
        response = client.get("/api/planning/project-123/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["project_id"] == "project-123"
        assert data["paper_count"] == 2
        assert data["question_count"] == 2
        assert data["gap_count"] == 1
        assert data["has_outline"] is True
        assert data["has_drafts"] is False
        assert data["questions"] == ["Question One", "Question Two"]


def test_generate_outline_success(tmp_path: Path) -> None:
    """Test outline generation successfully using mock LLM."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [{"doi": "10.1234/1", "title": "Paper 1"}]
    mock_neo4j.get_research_questions.return_value = [{"question_id": "q-1", "text": "Question One"}]
    app.state.neo4j_service = mock_neo4j

    mock_llm_instance = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "sections": [
            {"title": "Section 1", "description": "Desc 1", "assigned_papers": ["10.1234/1"], "theme": "Theme 1"}
        ],
        "narrative_arc": "The story arc."
    })
    mock_llm_instance.complete.return_value = mock_response
    app.state.llm_service = mock_llm_instance

    from config import Settings
    mock_settings = MagicMock(spec=Settings)
    mock_settings.projects_dir = str(tmp_path)

    with patch("config.get_settings", return_value=mock_settings):
        client = TestClient(app)
        response = client.post(
            "/api/planning/project-123/outline",
            json={"style": "thematic", "num_sections": 3},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "sections" in data
        assert len(data["sections"]) == 1
        assert data["sections"][0]["title"] == "Section 1"
        assert data["narrative_arc"] == "The story arc."
        assert data["style"] == "thematic"
        assert "saved_path" in data

        # Check outline was written to correct path on disk
        saved_file = Path(data["saved_path"])
        assert saved_file.exists()
        saved_data = json.loads(saved_file.read_text())
        assert saved_data["narrative_arc"] == "The story arc."
