"""Tests for BYOK Dual-Mode Authentication (Google AI Studio vs. Vertex AI).

Validates:
1. Environment variable propagation and SDK configuration for both modes.
2. LLMService initialization with Google AI Studio vs. Vertex AI clients.
3. GeminiEmbeddingProvider initialization with Google AI Studio vs. Vertex AI clients.
4. Handling of unconfigured credentials and placeholder detection.
5. Key masking and security safeguards.
6. Runtime hot-swapping and cache invalidation.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import BaseModel

from config import Settings, get_settings
from core.llm.models import CompletionRequest
from core.llm.service import LLMService
from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
from features.settings.router import _is_real_key, _mask_key


# ==============================================================================
# SECTION 1: ENVIRONMENT VARIABLE PROPAGATION
# ==============================================================================

def test_ai_studio_mode_env_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Google AI Studio mode sets correct OS environment variables."""
    monkeypatch.setenv("USE_VERTEX_AI", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestStudioKey123")
    monkeypatch.setenv("OPENALEX_API_KEY", "test-openalex")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-neo4j")
    monkeypatch.setenv("MYSQL_PASSWORD", "test-mysql")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.use_vertex_ai is False
    assert settings.gemini_api_key == "AIzaSyTestStudioKey123"
    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "FALSE"
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSyTestStudioKey123"
    assert os.environ.get("GOOGLE_API_KEY") == "AIzaSyTestStudioKey123"
    get_settings.cache_clear()


def test_vertex_ai_mode_env_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Vertex AI mode sets GCP Project and Location and unsets API keys."""
    monkeypatch.setenv("USE_VERTEX_AI", "true")
    monkeypatch.setenv("VERTEX_PROJECT", "enterprise-gcp-proj-99")
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west4")
    monkeypatch.setenv("OPENALEX_API_KEY", "test-openalex")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-neo4j")
    monkeypatch.setenv("MYSQL_PASSWORD", "test-mysql")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.use_vertex_ai is True
    assert settings.vertex_project == "enterprise-gcp-proj-99"
    assert settings.vertex_location == "europe-west4"
    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE"
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "enterprise-gcp-proj-99"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "europe-west4"
    assert os.environ.get("GEMINI_API_KEY") is None
    assert os.environ.get("GOOGLE_API_KEY") is None
    get_settings.cache_clear()


# ==============================================================================
# SECTION 2: LLM SERVICE INITIALIZATION & DUAL MODES
# ==============================================================================

def test_llm_service_initialization_ai_studio() -> None:
    """Test LLMService initializes genai.Client with API key in AI Studio mode."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "AIzaSy_Studio_Secret"
        mock_settings.return_value.vertex_project = None

        with patch("core.llm.service.genai.Client") as mock_client:
            service = LLMService(api_key="AIzaSy_Studio_Secret")
            mock_client.assert_called_once_with(api_key="AIzaSy_Studio_Secret")
            assert service._client is not None


def test_llm_service_initialization_vertex_ai() -> None:
    """Test LLMService initializes genai.Client with vertexai=True in Vertex AI mode."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "my-enterprise-project"
        mock_settings.return_value.vertex_location = "us-central1"
        mock_settings.return_value.gemini_api_key = None

        with patch("core.llm.service.genai.Client") as mock_client:
            service = LLMService()
            mock_client.assert_called_once_with(
                vertexai=True,
                project="my-enterprise-project",
                location="us-central1",
            )
            assert service._client is not None


def test_gemini_embedding_provider_initialization_ai_studio() -> None:
    """Test GeminiEmbeddingProvider initializes with api_key in AI Studio mode."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "AIzaSy_EmbeddingKey"

        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client:
            provider = GeminiEmbeddingProvider(api_key="AIzaSy_EmbeddingKey", output_dimensionality=768)
            mock_client.assert_called_once_with(api_key="AIzaSy_EmbeddingKey")
            assert provider.dimensions == 768


def test_gemini_embedding_provider_initialization_vertex_ai() -> None:
    """Test GeminiEmbeddingProvider initializes with vertex parameters in Vertex mode."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "gcp-embedding-project"
        mock_settings.return_value.vertex_location = "asia-east1"

        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client:
            provider = GeminiEmbeddingProvider(output_dimensionality=768)
            mock_client.assert_called_once_with(
                vertexai=True,
                project="gcp-embedding-project",
                location="asia-east1",
            )
            assert provider.dimensions == 768


# ==============================================================================
# SECTION 3: UNCONFIGURED & PLACEHOLDER HANDLING
# ==============================================================================

def test_llm_service_unconfigured_placeholder_sets_client_none() -> None:
    """Test that empty or placeholder keys result in _client = None."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "your_gemini_api_key_here"
        mock_settings.return_value.vertex_project = None

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            service = LLMService(api_key="your_gemini_api_key_here")
            assert service._client is None


@pytest.mark.asyncio
async def test_llm_service_complete_raises_value_error_when_unconfigured() -> None:
    """Test that calling complete on unconfigured LLMService raises ValueError."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = None
        mock_settings.return_value.vertex_project = None

        with patch.dict(os.environ, {}, clear=True):
            service = LLMService(api_key=None)
            assert service._client is None

            req = CompletionRequest(prompt="Hello Gemini")
            with pytest.raises(ValueError) as exc_info:
                await service.complete(req)
            assert "Gemini API key is not configured" in str(exc_info.value)


# ==============================================================================
# SECTION 4: KEY MASKING & SECURITY SAFEGUARDS
# ==============================================================================

def test_mask_key_standard_length() -> None:
    """Test masking a standard API key reveals only the last 4 characters."""
    raw_key = "AIzaSyABC123456789xyz"
    masked = _mask_key(raw_key)
    assert masked.endswith("9xyz")
    assert "AIzaSy" not in masked
    assert "•" in masked


def test_mask_key_short_length() -> None:
    """Test masking a short key (<= 4 chars) masks all characters completely."""
    assert _mask_key("abcd") == "****"
    assert _mask_key("123") == "****"
    assert _mask_key("x") == "****"


def test_mask_key_placeholder_and_empty() -> None:
    """Test masking placeholder values or empty string returns 'Not set'."""
    assert _mask_key("") == "Not set"
    assert _mask_key("your_gemini_api_key_here") == "Not set"
    assert _mask_key("your_openalex_api_key_here") == "Not set"


def test_is_real_key_detection() -> None:
    """Test _is_real_key accurately distinguishes valid keys from defaults."""
    assert _is_real_key("AIzaSyValidKey_123") is True
    assert _is_real_key("live_key_9999") is True
    assert _is_real_key("") is False
    assert _is_real_key("your_gemini_api_key_here") is False
    assert _is_real_key("your_openalex_api_key_here") is False


# ==============================================================================
# SECTION 5: RUNTIME HOT-SWAPPING
# ==============================================================================

def test_runtime_hot_swap_llm_service() -> None:
    """Test dynamic replacement of active LLMService in memory."""
    from main import app

    # Initial state: AI Studio service
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "key-v1"
        mock_settings.return_value.vertex_project = None

        with patch("core.llm.service.genai.Client"):
            service_v1 = LLMService(api_key="key-v1")
            app.state.llm_service = service_v1
            assert app.state.llm_service is service_v1

    # Hot-swap to Vertex AI service
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "hot-swap-project"
        mock_settings.return_value.vertex_location = "us-east4"
        mock_settings.return_value.gemini_api_key = None

        with patch("core.llm.service.genai.Client"):
            service_v2 = LLMService()
            app.state.llm_service = service_v2
            assert app.state.llm_service is service_v2
            assert app.state.llm_service is not service_v1


# ==============================================================================
# SECTION 6: LLM SERVICE COMPLETION & RETRY LOGIC
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_service_complete_success() -> None:
    """Test LLMService complete method with successful response."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("core.llm.service.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_result = MagicMock()
            mock_result.text = "Literature review response content"
            mock_result.usage_metadata.prompt_token_count = 50
            mock_result.usage_metadata.candidates_token_count = 150
            mock_result.usage_metadata.total_token_count = 200
            mock_client.models.generate_content.return_value = mock_result

            service = LLMService(api_key="dummy_key")
            req = CompletionRequest(prompt="Synthesize evidence")
            resp = await service.complete(req)

            assert resp.text == "Literature review response content"
            assert resp.usage.total_tokens == 200
            assert resp.usage.prompt_tokens == 50
            assert resp.usage.completion_tokens == 150


@pytest.mark.asyncio
async def test_llm_service_complete_retry_on_429() -> None:
    """Test LLMService exponential backoff retry on HTTP 429 status code."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("core.llm.service.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value

            class Mock429(Exception):
                code = 429

            mock_success = MagicMock()
            mock_success.text = "Recovered response"
            mock_success.usage_metadata = None

            mock_client.models.generate_content.side_effect = [Mock429("Rate limit"), mock_success]

            service = LLMService(api_key="dummy_key")
            req = CompletionRequest(prompt="Test prompt")

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                resp = await service.complete(req)
                assert resp.text == "Recovered response"
                assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_llm_service_complete_structured_parsing() -> None:
    """Test LLMService complete_structured parses JSON output into Pydantic model."""
    class ResearchOutline(BaseModel):
        title: str
        sections: list[str]

    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("core.llm.service.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_result = MagicMock()
            mock_result.text = '```json\n{"title": "GNN Survey", "sections": ["Intro", "Methods", "Conclusion"]}\n```'
            mock_result.usage_metadata = None
            mock_client.models.generate_content.return_value = mock_result

            service = LLMService(api_key="dummy_key")
            req = CompletionRequest(prompt="Generate outline")
            structured = await service.complete_structured(req, ResearchOutline)

            assert isinstance(structured.data, ResearchOutline)
            assert structured.data.title == "GNN Survey"
            assert structured.data.sections == ["Intro", "Methods", "Conclusion"]


# ==============================================================================
# SECTION 7: DUAL-MODE INSPECTION & PROBE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_service_complete_raises_value_error_when_unconfigured_vertex() -> None:
    """Test calling complete on unconfigured Vertex LLMService raises specific Vertex guidance."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = None

        with patch.dict(os.environ, {}, clear=True):
            service = LLMService(vertexai=True, project=None)
            assert service._client is None
            assert service.mode == "vertex"

            req = CompletionRequest(prompt="Hello Vertex")
            with pytest.raises(ValueError) as exc_info:
                await service.complete(req)
            assert "Vertex AI is enabled but project ID is missing" in str(exc_info.value)
            assert "gcloud auth application-default login" in str(exc_info.value)


def test_llm_service_properties_inspection() -> None:
    """Test LLMService properties accurately reflect configuration."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "my-gcp-proj"
        mock_settings.return_value.vertex_location = "us-east1"
        mock_settings.return_value.adk_model_name = "gemini-3.5-flash"

        with patch("core.llm.service.genai.Client"):
            service = LLMService(vertexai=True, project="my-gcp-proj", location="us-east1")
            assert service.is_configured is True
            assert service.mode == "vertex"
            assert service.project == "my-gcp-proj"
            assert service.location == "us-east1"
            assert service.model_name == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_llm_service_test_connection_class_method_studio() -> None:
    """Test LLMService.test_connection probe method for Studio."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "pong"
        mock_client.models.generate_content.return_value = mock_resp

        res = await LLMService.test_connection(
            mode="studio",
            api_key="AIzaSyValidKey",
        )
        assert res["success"] is True
        assert res["mode"] == "studio"
        assert "latency_ms" in res


@pytest.mark.asyncio
async def test_llm_service_test_connection_class_method_vertex() -> None:
    """Test LLMService.test_connection probe method for Vertex AI."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "pong"
        mock_client.models.generate_content.return_value = mock_resp

        res = await LLMService.test_connection(
            mode="vertex",
            project="test-proj-123",
            location="us-central1",
        )
        assert res["success"] is True
        assert res["mode"] == "vertex"
        assert "latency_ms" in res


def test_config_resolve_auth_mode_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Settings.resolve_auth_mode correctly infers studio vs vertex when USE_VERTEX_AI is omitted."""
    # When vertex_project is present and gemini_api_key is absent
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("USE_VERTEX_AI", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)

    s1 = Settings(
        vertex_project="gcp-auto-project",
        gemini_api_key=None,
        openalex_api_key="key",
        neo4j_password="pass",
        mysql_password="pass",
    )
    assert s1.use_vertex_ai is True

    # When gemini_api_key is present and vertex_project is absent
    s2 = Settings(
        gemini_api_key="AIzaSyAutoKey",
        vertex_project=None,
        openalex_api_key="key",
        neo4j_password="pass",
        mysql_password="pass",
    )
    assert s2.use_vertex_ai is False


