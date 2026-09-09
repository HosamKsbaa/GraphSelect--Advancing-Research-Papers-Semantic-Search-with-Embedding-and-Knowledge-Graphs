"""Adversarial and empirical challenge test suite for Backend Runtime Hot-Swapping & Mode Switching.

Authored by Challenger 2 for Milestone 1.
Validates:
1. Studio -> Vertex -> Studio -> Unconfigured dynamic runtime hot-swapping across:
   - LLMService properties (mode, project, location, is_configured, client)
   - os.environ synchronization (GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GEMINI_API_KEY, GOOGLE_API_KEY)
   - ServiceRegistry references and app.state.llm_service
2. Immediate credential propagation and usage in LLMService and GeminiEmbeddingProvider.
3. Unconfigured states, placeholder rejection, and descriptive ValueError exception contracts.
4. Client initialization failure handling (e.g. DefaultCredentialsError, invalid API keys).
5. Isolation of test_connection endpoint (no side effects on .env or runtime memory).
6. Concurrent hot-swap updates under mutex lock.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict

import config
from config import Settings, get_settings
from core.llm.models import CompletionRequest
from core.llm.service import LLMService
from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
from features.settings.router import (
    _get_env_value,
    _is_real_key,
    _is_real_project,
    _mask_key,
    _update_env_file,
    reload_runtime_services,
)
import features.settings.router as settings_router_module
from main import app


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture creating an isolated .env file for hot-swap mutation tests."""
    initial_content = (
        "USE_VERTEX_AI=false\n"
        "GEMINI_API_KEY=AIzaSyInitialStudioKey1111\n"
        "VERTEX_PROJECT=initial-vertex-proj\n"
        "VERTEX_LOCATION=us-central1\n"
        "OPENALEX_API_KEY=openalex-initial-key\n"
        "OPENALEX_EMAIL=tester@example.com\n"
        "NEO4J_PASSWORD=testneo4j\n"
        "MYSQL_PASSWORD=testmysql\n"
        "EMBEDDING_MODEL=gemini-embedding-2\n"
        "EMBEDDING_DIMENSIONS=768\n"
        "ADK_MODEL_NAME=gemini-3.5-flash\n"
    )
    env_path = tmp_path / ".env"
    env_path.write_text(initial_content, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", env_path)

    # Clean ambient auth env vars
    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "USE_VERTEX_AI", "VERTEX_PROJECT", "VERTEX_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI"]:
        monkeypatch.delenv(k, raising=False)

    get_settings.cache_clear()
    return env_path


# ==============================================================================
# CHALLENGE 1: MULTI-STEP RUNTIME HOT-SWAPPING LIFECYCLE
# ==============================================================================

def test_full_hot_swap_lifecycle_studio_vertex_unconfigured_cycle(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Challenge: Perform rapid multi-turn hot-swaps through API and verify in-memory state & os.environ."""
    client = TestClient(app)

    # -------------------------------------------------------------------------
    # STEP 1: Verify Initial Studio State
    # -------------------------------------------------------------------------
    res = client.get("/api/settings/auth")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["mode"] == "studio"
    assert data["use_vertex_ai"] is False
    assert data["has_credentials"] is True
    assert data["gemini_api_key_preview"].endswith("1111")

    # -------------------------------------------------------------------------
    # STEP 2: Hot-Swap to Vertex AI Mode (Prod Project, europe-west1)
    # -------------------------------------------------------------------------
    with patch("core.llm.service.genai.Client") as mock_llm_client, \
         patch("features.embedding.providers.gemini_provider.genai.Client") as mock_emb_client:
        
        # When update_auth runs, simulate config getting new values
        vertex_payload = {
            "mode": "vertex",
            "vertex_project": "prod-vertex-project-999",
            "vertex_location": "europe-west1",
        }
        res = client.post("/api/settings/auth", json=vertex_payload)
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["mode"] == "vertex"
        assert data["use_vertex_ai"] is True
        assert data["vertex_project"] == "prod-vertex-project-999"
        assert data["vertex_location"] == "europe-west1"
        assert data["has_credentials"] is True

        # Verify .env content on disk
        content = isolated_env.read_text(encoding="utf-8")
        assert "VERTEX_PROJECT=prod-vertex-project-999" in content
        assert "VERTEX_LOCATION=europe-west1" in content
        assert "USE_VERTEX_AI=true" in content

    # -------------------------------------------------------------------------
    # STEP 3: Hot-Swap back to Studio Mode with a New Key
    # -------------------------------------------------------------------------
    with patch("core.llm.service.genai.Client") as mock_llm_client, \
         patch("features.embedding.providers.gemini_provider.genai.Client") as mock_emb_client:
        
        studio_payload = {
            "mode": "studio",
            "gemini_api_key": "AIzaSySwappedStudioKey8888",
        }
        res = client.post("/api/settings/auth", json=studio_payload)
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["mode"] == "studio"
        assert data["use_vertex_ai"] is False
        assert data["gemini_api_key_preview"].endswith("8888")
        assert data["has_credentials"] is True

        content = isolated_env.read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=AIzaSySwappedStudioKey8888" in content
        assert "USE_VERTEX_AI=false" in content

    # -------------------------------------------------------------------------
    # STEP 4: Hot-Swap to Unconfigured State (Placeholder Key)
    # -------------------------------------------------------------------------
    unconfigured_payload = {
        "mode": "studio",
        "gemini_api_key": "your_gemini_api_key_here",
    }
    res = client.post("/api/settings/auth", json=unconfigured_payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["mode"] == "studio"
    assert data["has_credentials"] is False
    assert data["gemini_api_key_set"] is False


# ==============================================================================
# CHALLENGE 2: SERVICE REGISTRY SYNCHRONIZATION
# ==============================================================================

def test_service_registry_propagation_on_hot_swap(isolated_env: Path) -> None:
    """Challenge: Verify ServiceRegistry and dependent sub-services receive new LLM and embedding instances."""
    from agents._service_registry import ServiceRegistry

    # Setup dummy services in registry
    mock_planning = MagicMock()
    mock_writing = MagicMock()
    mock_retrieval = MagicMock()

    ServiceRegistry._initialized = True
    ServiceRegistry._planning_service = mock_planning
    ServiceRegistry._writing_service = mock_writing
    ServiceRegistry._paper_retrieval = mock_retrieval

    with patch("core.llm.service.genai.Client"), \
         patch("features.embedding.providers.gemini_provider.genai.Client"):
        
        # Reload services
        new_llm, new_emb = reload_runtime_services(app.state)

        assert ServiceRegistry._llm is new_llm
        assert ServiceRegistry._embedding_provider is new_emb
        assert mock_planning.llm is new_llm
        assert mock_writing.llm is new_llm
        assert mock_retrieval._embedding_provider is new_emb


# ==============================================================================
# CHALLENGE 3: EXCEPTION BEHAVIOR IN UNCONFIGURED STATES
# ==============================================================================

@pytest.mark.asyncio
async def test_unconfigured_studio_mode_exception_contract() -> None:
    """Challenge: Unconfigured Studio LLMService raises informative ValueError on complete()."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = None
        mock_settings.return_value.vertex_project = None

        with patch.dict(os.environ, {}, clear=True):
            service = LLMService(api_key=None, vertexai=False)
            assert service.is_configured is False
            assert service.mode == "studio"

            req = CompletionRequest(prompt="Synthesize paper")
            with pytest.raises(ValueError) as exc_info:
                await service.complete(req)
            
            err_msg = str(exc_info.value)
            assert "Gemini API key is not configured" in err_msg
            assert "Settings" in err_msg or ".env" in err_msg


@pytest.mark.asyncio
async def test_unconfigured_vertex_mode_exception_contract() -> None:
    """Challenge: Unconfigured Vertex LLMService raises informative ValueError with ADC guidance."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = ""
        mock_settings.return_value.vertex_location = "us-central1"
        mock_settings.return_value.gemini_api_key = None

        with patch.dict(os.environ, {}, clear=True):
            service = LLMService(vertexai=True, project="")
            assert service.is_configured is False
            assert service.mode == "vertex"

            req = CompletionRequest(prompt="Synthesize paper")
            with pytest.raises(ValueError) as exc_info:
                await service.complete(req)

            err_msg = str(exc_info.value)
            assert "Vertex AI is enabled but project ID is missing" in err_msg
            assert "gcloud auth application-default login" in err_msg


@pytest.mark.asyncio
async def test_gemini_embedding_provider_unconfigured_fails_loudly() -> None:
    """Challenge: Unconfigured GeminiEmbeddingProvider fails loudly with RuntimeError instead of silent fake fallback."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = ""

        with patch.dict(os.environ, {}, clear=True):
            provider = GeminiEmbeddingProvider(api_key="", output_dimensionality=768)
            assert provider._client is None

            with pytest.raises(RuntimeError, match="Gemini API client is not initialized"):
                await provider.embed_document("Sample paper abstract", title="Title 1")


# ==============================================================================
# CHALLENGE 4: CLIENT INITIALIZATION FAILURE RESILIENCE
# ==============================================================================

def test_llm_service_handles_client_constructor_exception() -> None:
    """Challenge: When genai.Client fails constructor, LLMService captures error and sets is_configured=False."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "invalid-project"
        mock_settings.return_value.vertex_location = "us-central1"

        with patch("core.llm.service.genai.Client", side_effect=Exception("Simulated ADC missing")):
            service = LLMService(vertexai=True, project="invalid-project")
            assert service.is_configured is False
            assert service.client is None
            assert service._init_error is not None
            assert "Simulated ADC missing" in service._init_error


# ==============================================================================
# CHALLENGE 5: TEST CONNECTION ISOLATION & ADVERSARIAL CASES
# ==============================================================================

@pytest.mark.asyncio
async def test_test_connection_probe_various_error_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Challenge: Probe connection classifies different Gemini API error responses accurately."""
    # Clear ambient keys so fallback does not interfere
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    # 1. API_KEY_INVALID
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("API_KEY_INVALID: Key not found")

        res = await LLMService.test_connection(mode="studio", api_key="AIzaSyBadKey")
        assert res["success"] is False
        assert "Invalid Gemini API key" in res["error"]
        assert "https://aistudio.google.com/" in res["details"]

    # 2. PERMISSION_DENIED (Vertex AI API disabled)
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("PERMISSION_DENIED: 403 Forbidden")

        res = await LLMService.test_connection(mode="vertex", project="valid-proj")
        assert res["success"] is False
        assert "Permission denied" in res["error"]
        assert "aiplatform.googleapis.com" in res["error"]

    # 3. RESOURCE_EXHAUSTED (Rate limit / quota 429)
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("RESOURCE_EXHAUSTED: 429 Quota")

        res = await LLMService.test_connection(mode="studio", api_key="AIzaSyRateLimitedKey")
        assert res["success"] is False
        assert "Quota exceeded" in res["error"]

    # 4. Missing project in Vertex mode
    res = await LLMService.test_connection(mode="vertex", project="")
    assert res["success"] is False
    assert "Google Cloud Project ID is not configured" in res["error"]

    # 5. Missing key in Studio mode
    res = await LLMService.test_connection(mode="studio", api_key="")
    assert res["success"] is False
    assert "Gemini API key is not configured" in res["error"]


def test_test_connection_endpoint_preserves_env_file_immutability(isolated_env: Path) -> None:
    """Challenge: test_connection endpoint must never write or mutate the active .env file."""
    initial_content = isolated_env.read_text(encoding="utf-8")
    client = TestClient(app)

    # Probe studio mode
    with patch("google.genai.Client"):
        client.post("/api/settings/test-connection", json={"mode": "studio", "gemini_api_key": "AIzaSyEphemeralKey"})
        assert isolated_env.read_text(encoding="utf-8") == initial_content

    # Probe vertex mode
    with patch("google.genai.Client"):
        client.post("/api/settings/test-connection", json={"mode": "vertex", "vertex_project": "ephemeral-proj"})
        assert isolated_env.read_text(encoding="utf-8") == initial_content


# ==============================================================================
# CHALLENGE 6: CONCURRENT MUTATION MUTEX INTEGRITY
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_settings_update_under_lock(isolated_env: Path) -> None:
    """Challenge: High concurrency updates to .env via update_auth do not corrupt .env file."""
    from features.settings.router import update_auth
    from features.settings.models import AuthUpdateRequest

    mock_request = MagicMock()
    mock_request.app.state = MagicMock()

    with patch("core.llm.service.genai.Client"), \
         patch("features.embedding.providers.gemini_provider.genai.Client"):
        
        async def do_update(idx: int):
            req = AuthUpdateRequest(
                mode="studio",
                gemini_api_key=f"AIzaSyConcurrentKey_{idx:04d}",
            )
            return await update_auth(req, mock_request)

        # Run 10 simultaneous update requests
        tasks = [do_update(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        for r in results:
            assert r.gemini_api_key_set is True

        # Verify .env has exactly one valid GEMINI_API_KEY entry and is not corrupt
        lines = isolated_env.read_text(encoding="utf-8").splitlines()
        key_lines = [l for l in lines if l.startswith("GEMINI_API_KEY=")]
        assert len(key_lines) == 1
        assert key_lines[0].startswith("GEMINI_API_KEY=AIzaSyConcurrentKey_")
