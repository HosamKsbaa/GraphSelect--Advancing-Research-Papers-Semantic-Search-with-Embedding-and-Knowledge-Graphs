"""Integration and unit tests for the settings router and .env persistence.

Tests cover:
1. GET /api/settings (reading masked API keys and system configuration).
2. PUT /api/settings (updating API keys, partial updates, and .env synchronization).
3. Helper functions: _read_env_lines, _get_env_value, _update_env_file, _mask_key, _is_real_key.
4. GET /api/settings/auth (dual-mode authentication status).
5. POST /api/settings/test-connection (connection testing for AI Studio and Vertex AI).
6. POST /api/settings/auth (persisting dual-mode credentials).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
import features.settings.router as settings_router_module
from features.settings.router import (
    _get_env_value,
    _is_real_key,
    _mask_key,
    _read_env_lines,
    _update_env_file,
)


@pytest.fixture
def mock_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture providing an isolated temporary .env file for testing."""
    env_content = (
        "# Application Environment Variables\n"
        "GEMINI_API_KEY=AIzaSyInitialTestKey1234\n"
        "# OpenAlex Configuration\n"
        "OPENALEX_API_KEY=openalex-secret-key-9999\n"
        "OPENALEX_EMAIL=researcher@university.edu\n"
        "NEO4J_PASSWORD=test-neo4j-pass\n"
        "MYSQL_PASSWORD=test-mysql-pass\n"
    )
    test_env = tmp_path / ".env"
    test_env.write_text(env_content, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", test_env)
    return test_env


# ==============================================================================
# SECTION 1: GET /api/settings ENDPOINT
# ==============================================================================

def test_get_settings_success(mock_env_file: Path) -> None:
    """Test GET /api/settings returns masked keys and configuration metadata."""
    client = TestClient(app)
    response = client.get("/api/settings")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["gemini_api_key_set"] is True
    assert data["gemini_api_key_preview"].endswith("1234")
    assert "AIzaSy" not in data["gemini_api_key_preview"]

    assert data["openalex_api_key_set"] is True
    assert data["openalex_api_key_preview"].endswith("9999")
    assert "secret" not in data["openalex_api_key_preview"]

    assert data["openalex_email"] == "researcher@university.edu"
    assert "embedding_model" in data
    assert "embedding_dimensions" in data


def test_get_settings_with_placeholder_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GET /api/settings correctly identifies placeholder keys as unset."""
    placeholder_env = (
        "GEMINI_API_KEY=your_gemini_api_key_here\n"
        "OPENALEX_API_KEY=your_openalex_api_key_here\n"
        "OPENALEX_EMAIL=\n"
    )
    test_env = tmp_path / ".env"
    test_env.write_text(placeholder_env, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", test_env)

    client = TestClient(app)
    response = client.get("/api/settings")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["gemini_api_key_set"] is False
    assert data["gemini_api_key_preview"] == "Not set"
    assert data["openalex_api_key_set"] is False
    assert data["openalex_api_key_preview"] == "Not set"
    assert data["openalex_email"] == ""


# ==============================================================================
# SECTION 2: PUT /api/settings ENDPOINT
# ==============================================================================

def test_update_settings_partial_gemini_key(mock_env_file: Path) -> None:
    """Test updating only the Gemini API key preserves OpenAlex configuration."""
    client = TestClient(app)
    payload = {"gemini_api_key": "AIzaSyUpdatedKey8888"}

    response = client.put("/api/settings", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["restart_required"] is False
    assert "Gemini API key" in data["message"]

    # Verify .env content
    content = mock_env_file.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=AIzaSyUpdatedKey8888" in content
    assert "OPENALEX_API_KEY=openalex-secret-key-9999" in content
    assert "OPENALEX_EMAIL=researcher@university.edu" in content


def test_update_settings_clear_email(mock_env_file: Path) -> None:
    """Test clearing OpenAlex email by sending an empty string."""
    client = TestClient(app)
    payload = {"openalex_email": ""}

    response = client.put("/api/settings", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True

    content = mock_env_file.read_text(encoding="utf-8")
    assert "OPENALEX_EMAIL=" in content


def test_update_settings_no_changes(mock_env_file: Path) -> None:
    """Test sending empty update payload returns success without restart."""
    client = TestClient(app)
    response = client.put("/api/settings", json={})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["restart_required"] is False
    assert data["message"] == "No changes to apply"


def test_update_settings_handles_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test PUT /api/settings raises 500 when .env cannot be written."""
    def mock_failing_update(*args, **kwargs):
        raise OSError("Read-only filesystem")

    monkeypatch.setattr(settings_router_module, "_update_env_file", mock_failing_update)

    client = TestClient(app)
    response = client.put("/api/settings", json={"gemini_api_key": "new-key"})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to write settings" in response.json()["detail"]


# ==============================================================================
# SECTION 3: LOW-LEVEL .ENV HELPER FUNCTIONS
# ==============================================================================

def test_read_env_lines_nonexistent_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _read_env_lines returns empty list when .env file does not exist."""
    missing_file = tmp_path / "nonexistent.env"
    monkeypatch.setattr(settings_router_module, "ENV_FILE", missing_file)
    assert _read_env_lines() == []


def test_get_env_value_case_insensitive_and_comments(mock_env_file: Path) -> None:
    """Test _get_env_value correctly ignores comments and performs case-insensitive lookup."""
    assert _get_env_value("gemini_api_key") == "AIzaSyInitialTestKey1234"
    assert _get_env_value("GEMINI_API_KEY") == "AIzaSyInitialTestKey1234"
    assert _get_env_value("openalex_email") == "researcher@university.edu"
    assert _get_env_value("NONEXISTENT_KEY") == ""


def test_update_env_file_appends_new_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _update_env_file appends new keys that were not originally present."""
    initial_content = "# Initial Config\nEXISTING_KEY=val1\n"
    test_env = tmp_path / ".env"
    test_env.write_text(initial_content, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", test_env)

    _update_env_file({"NEW_SETTING": "new_value", "EXISTING_KEY": "updated_val1"})

    lines = test_env.read_text(encoding="utf-8").splitlines()
    assert "# Initial Config" in lines
    assert "EXISTING_KEY=updated_val1" in lines
    assert "NEW_SETTING=new_value" in lines


# ==============================================================================
# SECTION 4: TEST CONNECTION & DUAL-MODE AUTH CONTRACTS
# ==============================================================================

def test_test_connection_ai_studio_success() -> None:
    """Test connection validation for Google AI Studio mode with mock client."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "Pong"
        mock_client.models.generate_content.return_value = mock_resp

        payload = {
            "mode": "studio",
            "gemini_api_key": "AIzaSyValidTestingKey",
        }
        response = client.post("/api/settings/test-connection", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "latency_ms" in data


def test_test_connection_ai_studio_invalid_key() -> None:
    """Test connection validation failure when Gemini API key is invalid."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("API_KEY_INVALID: 400 Bad Request")

        payload = {
            "mode": "studio",
            "gemini_api_key": "AIzaSyInvalidKey",
        }
        response = client.post("/api/settings/test-connection", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert "error" in data or "message" in data


def test_test_connection_vertex_ai_success() -> None:
    """Test connection validation for Vertex AI mode with mock GCP client."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "Pong from Vertex"
        mock_client.models.generate_content.return_value = mock_resp

        payload = {
            "mode": "vertex",
            "vertex_project": "test-gcp-project",
            "vertex_location": "us-central1",
        }
        response = client.post("/api/settings/test-connection", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "latency_ms" in data


def test_test_connection_vertex_ai_permission_denied() -> None:
    """Test connection validation failure when Vertex AI lacks ADC or permission."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("DefaultCredentialsError: ADC not found")

        payload = {
            "mode": "vertex",
            "vertex_project": "missing-adc-project",
            "vertex_location": "us-central1",
        }
        response = client.post("/api/settings/test-connection", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False


def test_test_connection_does_not_mutate_env(mock_env_file: Path) -> None:
    """Verify that testing a connection does not modify .env file."""
    initial_content = mock_env_file.read_text(encoding="utf-8")
    client = TestClient(app)

    payload = {
        "mode": "studio",
        "gemini_api_key": "AIzaSyTemporaryProbeKey",
    }
    client.post("/api/settings/test-connection", json=payload)

    current_content = mock_env_file.read_text(encoding="utf-8")
    assert current_content == initial_content


# ==============================================================================
# SECTION 5: GET / POST /api/settings/auth ENDPOINTS
# ==============================================================================

def test_get_auth_status_studio_mode(mock_env_file: Path) -> None:
    """Test GET /api/settings/auth returns Google AI Studio status."""
    client = TestClient(app)
    response = client.get("/api/settings/auth")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["mode"] == "studio"
    assert data["has_credentials"] is True
    assert data["use_vertex_ai"] is False
    assert data["gemini_api_key_preview"].endswith("1234")
    assert data["gemini_api_key_set"] is True
    assert data["vertex_project"] is None


def test_get_auth_status_vertex_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GET /api/settings/auth returns Vertex AI status when configured."""
    vertex_env = (
        "USE_VERTEX_AI=true\n"
        "VERTEX_PROJECT=enterprise-research-prod\n"
        "VERTEX_LOCATION=europe-west1\n"
        "OPENALEX_API_KEY=test-key\n"
    )
    test_env = tmp_path / ".env"
    test_env.write_text(vertex_env, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", test_env)

    client = TestClient(app)
    response = client.get("/api/settings/auth")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["mode"] == "vertex"
    assert data["has_credentials"] is True
    assert data["use_vertex_ai"] is True
    assert data["vertex_project"] == "enterprise-research-prod"
    assert data["vertex_location"] == "europe-west1"


def test_post_auth_updates_env_and_reloads_studio(mock_env_file: Path) -> None:
    """Test POST /api/settings/auth updates .env and hot-swaps to Studio mode."""
    client = TestClient(app)
    payload = {
        "mode": "studio",
        "gemini_api_key": "AIzaSyBrandNewKey9999",
    }

    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mode"] == "studio"
        assert data["use_vertex_ai"] is False
        assert data["gemini_api_key_preview"].endswith("9999")
        assert data["has_credentials"] is True

        content = mock_env_file.read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=AIzaSyBrandNewKey9999" in content
        assert "USE_VERTEX_AI=false" in content


def test_post_auth_updates_env_and_reloads_vertex(mock_env_file: Path) -> None:
    """Test POST /api/settings/auth updates .env and hot-swaps to Vertex mode."""
    client = TestClient(app)
    payload = {
        "mode": "vertex",
        "vertex_project": "my-swapped-gcp-project",
        "vertex_location": "us-east4",
    }

    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mode"] == "vertex"
        assert data["use_vertex_ai"] is True
        assert data["vertex_project"] == "my-swapped-gcp-project"
        assert data["vertex_location"] == "us-east4"
        assert data["has_credentials"] is True

        content = mock_env_file.read_text(encoding="utf-8")
        assert "VERTEX_PROJECT=my-swapped-gcp-project" in content
        assert "VERTEX_LOCATION=us-east4" in content
        assert "USE_VERTEX_AI=true" in content

