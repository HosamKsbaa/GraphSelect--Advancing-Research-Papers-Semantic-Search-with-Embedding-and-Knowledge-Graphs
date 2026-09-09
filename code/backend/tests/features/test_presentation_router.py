"""Contract and integration tests for FastAPI Presentation REST Endpoints and Services (User Story 4).

Validates POST/GET presentation deck endpoints, error mappings, PDF export, and Neo4j persistence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from features.export.presentation_models import (
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationSlide,
    PresentationTheme,
    PresenterNotes,
    SlideLayoutType,
)
from features.export.presentation_service import PresentationService
from main import app


@pytest.fixture
def client_with_mock_state(mock_presentation_neo4j_service: Any, tmp_path: Path) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with injected mock Neo4j service and tmp projects directory."""
    app.state.neo4j_service = mock_presentation_neo4j_service
    app.state.log_service = None
    progress_mock = AsyncMock()
    progress_mock.publish = AsyncMock()
    app.state.progress_service = progress_mock

    from config import get_settings
    settings = get_settings()
    with patch.object(settings, "projects_dir", str(tmp_path / "campaigns")):
        yield TestClient(app)


def test_post_generate_presentation_success(client_with_mock_state: TestClient) -> None:
    """Verify POST /api/export/{project_id}/presentation generates deck and returns 200."""
    payload = {
        "project_id": "test-campaign-001",
        "audience_profile": "supervisor",
        "target_slide_count": 10,
        "theme": "dark",
        "enable_mermaid": True,
    }
    response = client_with_mock_state.post("/api/export/test-campaign-001/presentation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["slide_count"] == 10
    assert Path(data["file_path"]).exists()
    assert len(data["sha256_hash"]) == 64


def test_post_generate_presentation_project_not_found(client_with_mock_state: TestClient) -> None:
    """Verify POST /api/export/{project_id}/presentation returns 404 for unknown project."""
    payload = {
        "project_id": "non-existent-campaign",
        "audience_profile": "supervisor",
        "target_slide_count": 10,
    }
    response = client_with_mock_state.post("/api/export/non-existent-campaign/presentation", json=payload)
    assert response.status_code == 404
    err = response.json()["detail"]
    assert err["code"] == "PROJECT_NOT_FOUND"


def test_post_generate_presentation_invalid_slide_count(client_with_mock_state: TestClient) -> None:
    """Verify POST /api/export/{project_id}/presentation returns 422/400 for out-of-bound slide count."""
    payload = {
        "project_id": "test-campaign-001",
        "audience_profile": "supervisor",
        "target_slide_count": 3,
    }
    response = client_with_mock_state.post("/api/export/test-campaign-001/presentation", json=payload)
    # FastAPI schema validation returns 422 for ge/le violations
    assert response.status_code in [400, 422]


def test_list_and_get_latest_presentations(
    client_with_mock_state: TestClient,
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify GET /api/export/{project_id}/presentations and /latest return deck metadata."""
    # Seed mock response for list query
    mock_deck = {
        "artifact_id": "deck-test-1",
        "project_id": "test-campaign-001",
        "file_path": "/tmp/deck.html",
        "file_size_bytes": 1024,
        "sha256_hash": "abc123hash",
        "slide_count": 12,
        "audience_profile": "supervisor",
        "theme": "dark",
        "facts_verified_count": 12,
        "created_at": "2026-09-09T18:00:00Z",
    }
    mock_presentation_neo4j_service.execute_read = AsyncMock(return_value=[mock_deck])

    resp_list = client_with_mock_state.get("/api/export/test-campaign-001/presentations")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    resp_latest = client_with_mock_state.get("/api/export/test-campaign-001/presentation/latest")
    assert resp_latest.status_code == 200
    assert resp_latest.json()["artifact_id"] == "deck-test-1"


def test_download_presentation_html(
    client_with_mock_state: TestClient,
    mock_presentation_neo4j_service: Any,
    tmp_path: Path,
) -> None:
    """Verify GET /api/export/{project_id}/presentation/{artifact_id}/download serves HTML file."""
    html_file = tmp_path / "presentation_2026.html"
    html_file.write_text("<!DOCTYPE html><html><body>Deck</body></html>", encoding="utf-8")

    mock_deck = {
        "artifact_id": "deck-download-1",
        "project_id": "test-campaign-001",
        "file_path": str(html_file),
        "file_size_bytes": html_file.stat().st_size,
        "sha256_hash": "abc123",
        "slide_count": 10,
        "audience_profile": "supervisor",
        "theme": "dark",
        "facts_verified_count": 5,
        "created_at": "2026-09-09T18:00:00Z",
    }
    mock_presentation_neo4j_service.execute_read = AsyncMock(return_value=[mock_deck])

    resp = client_with_mock_state.get("/api/export/test-campaign-001/presentation/deck-download-1/download")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Deck" in resp.text


def test_get_presentation_pdf_success(
    client_with_mock_state: TestClient,
    mock_presentation_neo4j_service: Any,
    tmp_path: Path,
) -> None:
    """Verify GET .../pdf returns 200 and application/pdf on successful compilation."""
    html_file = tmp_path / "presentation_source.html"
    html_file.write_text("<!DOCTYPE html><html><body>PDF Source</body></html>", encoding="utf-8")
    mock_deck = {
        "artifact_id": "deck-pdf-1",
        "project_id": "test-campaign-001",
        "file_path": str(html_file),
        "file_size_bytes": html_file.stat().st_size,
        "sha256_hash": "sha123",
        "slide_count": 10,
        "audience_profile": "supervisor",
        "theme": "dark",
        "facts_verified_count": 5,
        "created_at": "2026-09-09T18:00:00Z",
    }
    mock_presentation_neo4j_service.execute_read = AsyncMock(return_value=[mock_deck])

    with patch.object(PresentationService, "export_deck_to_pdf", new_callable=AsyncMock) as mock_export:
        pdf_file = html_file.with_suffix(".pdf")
        pdf_file.write_bytes(b"%PDF-1.4 mock pdf content")
        mock_export.return_value = str(pdf_file)

        resp = client_with_mock_state.get("/api/export/test-campaign-001/presentation/deck-pdf-1/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]


def test_get_presentation_pdf_not_found(
    client_with_mock_state: TestClient,
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify GET .../pdf returns 404 when deck does not exist."""
    mock_presentation_neo4j_service.execute_read = AsyncMock(return_value=[])
    resp = client_with_mock_state.get("/api/export/test-campaign-001/presentation/missing-deck/pdf")
    assert resp.status_code == 404


def test_get_presentation_pdf_compilation_failure(
    client_with_mock_state: TestClient,
    mock_presentation_neo4j_service: Any,
    tmp_path: Path,
) -> None:
    """Verify GET .../pdf returns 422 when PDF export fails."""
    html_file = tmp_path / "presentation_bad.html"
    html_file.write_text("<!DOCTYPE html><html><body>Bad Source</body></html>", encoding="utf-8")
    mock_deck = {
        "artifact_id": "deck-pdf-bad",
        "project_id": "test-campaign-001",
        "file_path": str(html_file),
        "file_size_bytes": html_file.stat().st_size,
        "sha256_hash": "sha123",
        "slide_count": 10,
        "audience_profile": "supervisor",
        "theme": "dark",
        "facts_verified_count": 5,
        "created_at": "2026-09-09T18:00:00Z",
    }
    mock_presentation_neo4j_service.execute_read = AsyncMock(return_value=[mock_deck])

    with patch.object(PresentationService, "export_deck_to_pdf", side_effect=RuntimeError("Headless browser error")):
        resp = client_with_mock_state.get("/api/export/test-campaign-001/presentation/deck-pdf-bad/pdf")
        assert resp.status_code == 422
        assert "PDF compilation failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_service_generate_deck(
    mock_presentation_neo4j_service: Any,
    tmp_path: Path,
) -> None:
    """Verify PresentationService.generate_deck generates HTML and persists to disk."""
    service = PresentationService(
        neo4j=mock_presentation_neo4j_service,
        projects_dir=tmp_path / "campaigns",
    )
    req = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        target_slide_count=8,
    )
    resp = await service.generate_deck(req)
    assert resp.success is True
    assert resp.slide_count == 8
    assert Path(resp.file_path).exists()


@pytest.mark.asyncio
async def test_export_pdf(
    tmp_path: Path,
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify export_deck_to_pdf creates a valid 16:9 PDF using headless browser."""
    html_file = tmp_path / "test_slide.html"
    html_file.write_text(
        "<!DOCTYPE html><html><head><style>@page { size: 16in 9in landscape; }</style></head><body><h1>Slide 1</h1></body></html>",
        encoding="utf-8",
    )
    out_pdf = tmp_path / "test_slide.pdf"

    service = PresentationService(
        neo4j=mock_presentation_neo4j_service,
        projects_dir=tmp_path,
    )
    pdf_res = await service.export_deck_to_pdf(str(html_file), str(out_pdf))
    assert Path(pdf_res).exists()
    assert Path(pdf_res).stat().st_size > 0


@pytest.mark.asyncio
async def test_neo4j_persistence(
    mock_presentation_neo4j_service: Any,
    tmp_path: Path,
) -> None:
    """Verify persist_presentation_to_graph executes Query 7 Cypher MERGE statements."""
    service = PresentationService(
        neo4j=mock_presentation_neo4j_service,
        projects_dir=tmp_path,
    )
    req = PresentationDeckRequest(project_id="test-campaign-001")
    slides = [
        PresentationSlide(
            slide_id="s-p1",
            index=1,
            title="Persisted Slide",
            category="Test",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>Test</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Point"],
                estimated_duration_seconds=60,
            ),
            grounding_provenance=["10.1145/3292500.3330919"],
        )
    ]
    test_file = tmp_path / "test.html"
    test_file.write_text("dummy", encoding="utf-8")

    await service.persist_presentation_to_graph("deck-123", req, slides, test_file, "hash123")
    assert mock_presentation_neo4j_service.execute_write.called
    call_query = mock_presentation_neo4j_service.execute_write.call_args[0][0]
    assert "PresentationDeck" in call_query
    assert "CONTAINS_SLIDE" in call_query
    assert "GROUNDED_IN" in call_query
