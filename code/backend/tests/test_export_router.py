"""Integration tests for the export router REST endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_export_bibtex_success(tmp_path: Path) -> None:
    """Test exporting project references to BibTeX format successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [
        {
            "doi": "10.1234/test",
            "title": "A GNN Paper",
            "year": 2022,
            "cited_by_count": 10,
            "source": "openalex",
            "authors": ["Alice Smith"],
            "venue": "Nature",
        }
    ]
    app.state.neo4j_service = mock_neo4j

    from config import get_settings
    settings = get_settings()
    old_dir = settings.projects_dir
    settings.projects_dir = str(tmp_path)

    try:
        client = TestClient(app)
        response = client.post("/api/export/project-123/bibtex")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["entry_count"] == 1
        assert "saved_path" in data
        assert "bibtex_preview" in data

        # Check references.bib was saved correctly
        saved_file = Path(data["saved_path"])
        assert saved_file.exists()
        assert "@article" in saved_file.read_text(encoding="utf-8")
    finally:
        settings.projects_dir = old_dir


def test_export_latex_success(tmp_path: Path) -> None:
    """Test exporting approved drafts to LaTeX document format successfully."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [
        {
            "doi": "10.1234/test",
            "title": "A GNN Paper",
            "year": 2022,
            "cited_by_count": 10,
            "source": "openalex",
            "authors": ["Alice Smith"],
            "venue": "Nature",
        }
    ]
    app.state.neo4j_service = mock_neo4j

    # Setup drafts on disk in the mocked projects directory
    project_dir = tmp_path / "project-123"
    drafts_dir = project_dir / "drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "introduction.md").write_text("This is an introduction paragraph citing 10.1234/test.")

    from config import get_settings
    settings = get_settings()
    old_dir = settings.projects_dir
    settings.projects_dir = str(tmp_path)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/export/project-123/latex",
            json={"template": "ieee"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["template"] == "ieee"
        assert data["section_count"] == 1
        assert "tex_path" in data
        assert "bib_path" in data
        assert "latex_preview" in data

        # Verify output files exist
        assert Path(data["tex_path"]).exists()
        assert Path(data["bib_path"]).exists()
        assert "\\documentclass" in Path(data["tex_path"]).read_text(encoding="utf-8")
    finally:
        settings.projects_dir = old_dir


def test_export_citation_graph_success(tmp_path: Path) -> None:
    """Test exporting the citation graph successfully as JSON + GraphML."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_citation_graph_nodes.return_value = [
        {"doi": "10.1234/1", "title": "Paper One", "year": 2020, "cited_by_count": 5},
        {"doi": "10.1234/2", "title": "Paper Two", "year": 2021, "cited_by_count": 8},
    ]
    mock_neo4j.get_citation_graph_edges.return_value = [
        {"source": "10.1234/1", "target": "10.1234/2"},
    ]
    app.state.neo4j_service = mock_neo4j

    from config import get_settings
    settings = get_settings()
    old_dir = settings.projects_dir
    settings.projects_dir = str(tmp_path)

    try:
        client = TestClient(app)
        response = client.post("/api/export/project-123/citation-graph")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["node_count"] == 2
        assert data["edge_count"] == 1
        assert "json_path" in data
        assert "graphml_path" in data

        # Check graph.json content
        json_file = Path(data["json_path"])
        assert json_file.exists()
        graph_data = json.loads(json_file.read_text())
        assert len(graph_data["nodes"]) == 2
        assert len(graph_data["links"]) == 1

        # Check graph.graphml content
        graphml_file = Path(data["graphml_path"])
        assert graphml_file.exists()
        assert "<graphml" in graphml_file.read_text(encoding="utf-8")
    finally:
        settings.projects_dir = old_dir
