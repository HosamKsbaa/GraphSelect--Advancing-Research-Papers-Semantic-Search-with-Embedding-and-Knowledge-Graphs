"""FastAPI settings router for ALRS v2 backend.

Exposes endpoints to read, test, and update application configuration and
dual-mode authentication (Google AI Studio vs. Vertex AI) stored in .env.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status

from config import find_env_file, get_settings
from features.settings.models import (
    AuthStatusResponse,
    AuthUpdateRequest,
    AvailableModelsResponse,
    ModelInfo,
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE = find_env_file()

# Mutex to guard concurrent .env file writes
_ENV_WRITE_LOCK = asyncio.Lock()

# Sentinel values that ship in default configuration
_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_openalex_api_key_here", "test-openalex-key", "test_openalex_key", "dev-dummy-openalex-key", "none"}
_PLACEHOLDER_PROJECTS = {"", "your-gcp-project-id", "your_project_id_here", "test-project", "none"}


# ── Helpers ──────────────────────────────────────────────────────────

def _clean_key_value(key: str, value: str) -> tuple[str, str]:
    """Sanitize env key and value to prevent CRLF / newline injection and file corruption.

    - Keys: Stripped of whitespace, newlines, null bytes, and '=' characters.
    - Values: Truncated at first newline/CRLF and stripped to guarantee single-line
      persistence without injecting arbitrary environment variables.
    """
    clean_key = (
        str(key)
        .replace("\r", "")
        .replace("\n", "")
        .replace("\0", "")
        .replace("=", "")
        .strip()
    )
    raw_val = str(value).replace("\0", "")
    clean_val = raw_val.split("\r")[0].split("\n")[0].strip()
    return clean_key, clean_val


def _set_env_line(key: str, value: str) -> str:
    """Format and return a single sanitized KEY=VALUE line for .env persistence."""
    clean_key, clean_val = _clean_key_value(key, value)
    return f"{clean_key}={clean_val}"


def _mask_key(key: str | None) -> str:
    """Return a masked preview of an API key, showing only the last 4 chars."""
    if not key or key.strip() in _PLACEHOLDER_KEYS:
        return "Not set"
    raw = key.strip()
    if len(raw) <= 4:
        return "****"
    return "•" * min(len(raw) - 4, 20) + raw[-4:]


def _is_real_key(key: str | None) -> bool:
    """Check whether key is a genuine API key (not empty or placeholder)."""
    return bool(key and key.strip() and key.strip() not in _PLACEHOLDER_KEYS)


def _is_real_project(project: str | None) -> bool:
    """Check whether project is a genuine GCP project ID."""
    return bool(project and project.strip() and project.strip() not in _PLACEHOLDER_PROJECTS)


def _read_env_lines() -> list[str]:
    """Read all lines from .env without trailing newlines."""
    target_file = ENV_FILE if isinstance(ENV_FILE, Path) else Path(ENV_FILE)
    if not target_file.exists():
        return []
    return target_file.read_text(encoding="utf-8").splitlines()


def _get_env_value(key: str) -> str:
    """Read a specific key value from .env (case-insensitive)."""
    for line in _read_env_lines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip().upper() == key.upper():
            return v.strip()
    return ""


def _update_env_file(updates: dict[str, str]) -> None:
    """Update specific keys in .env preserving formatting, comments, and structure."""
    target_file = ENV_FILE if isinstance(ENV_FILE, Path) else Path(ENV_FILE)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    lines = _read_env_lines()

    # Pre-clean all incoming update pairs
    sanitized_updates: dict[str, str] = {}
    for raw_k, raw_v in updates.items():
        k, v = _clean_key_value(raw_k, str(raw_v) if raw_v is not None else "")
        if k:
            sanitized_updates[k] = v

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        k, _, _ = stripped.partition("=")
        key_name = k.strip()

        matched_update_key = None
        for update_key in sanitized_updates:
            if update_key.upper() == key_name.upper():
                matched_update_key = update_key
                break

        if matched_update_key is not None:
            new_lines.append(_set_env_line(key_name, sanitized_updates[matched_update_key]))
            updated_keys.add(matched_update_key.upper())
        else:
            new_lines.append(line)

    for key, val in sanitized_updates.items():
        if key.upper() not in updated_keys:
            new_lines.append(_set_env_line(key, val))

    target_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def sync_os_environ_from_env() -> None:
    """Read the active canonical .env file and synchronize all runtime auth env vars."""
    use_vertex_raw = _get_env_value("USE_VERTEX_AI")
    gemini_key = _get_env_value("GEMINI_API_KEY")
    vertex_project = _get_env_value("VERTEX_PROJECT")
    vertex_location = _get_env_value("VERTEX_LOCATION") or "us-central1"
    openalex_key = _get_env_value("OPENALEX_API_KEY")
    openalex_email = _get_env_value("OPENALEX_EMAIL")

    _, gemini_clean = _clean_key_value("GEMINI_API_KEY", gemini_key)
    _, proj_clean = _clean_key_value("VERTEX_PROJECT", vertex_project)
    _, loc_clean = _clean_key_value("VERTEX_LOCATION", vertex_location)
    _, openalex_clean = _clean_key_value("OPENALEX_API_KEY", openalex_key)
    _, email_clean = _clean_key_value("OPENALEX_EMAIL", openalex_email)

    is_vertex = use_vertex_raw.lower() in ("true", "1", "yes")

    if is_vertex:
        os.environ["USE_VERTEX_AI"] = "true"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if proj_clean and proj_clean not in _PLACEHOLDER_PROJECTS:
            os.environ["VERTEX_PROJECT"] = proj_clean
            os.environ["GOOGLE_CLOUD_PROJECT"] = proj_clean
        else:
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("VERTEX_PROJECT", None)

        if loc_clean:
            os.environ["VERTEX_LOCATION"] = loc_clean
            os.environ["GOOGLE_CLOUD_LOCATION"] = loc_clean

        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
    else:
        os.environ["USE_VERTEX_AI"] = "false"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        if gemini_clean and gemini_clean not in _PLACEHOLDER_KEYS:
            os.environ["GEMINI_API_KEY"] = gemini_clean
            os.environ["GOOGLE_API_KEY"] = gemini_clean
        else:
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)

        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("VERTEX_PROJECT", None)

    if openalex_clean and openalex_clean not in _PLACEHOLDER_KEYS:
        os.environ["OPENALEX_API_KEY"] = openalex_clean
    if email_clean:
        os.environ["OPENALEX_EMAIL"] = email_clean


def reload_runtime_services(app_state: Any = None) -> tuple[Any, Any]:
    """Hot-swap runtime LLM and embedding services across app.state and ServiceRegistry."""
    from config import get_settings
    from core.llm.service import LLMService
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
    from agents._service_registry import ServiceRegistry

    # 1. Sync os.environ before clearing Settings singleton
    sync_os_environ_from_env()

    # 2. Clear cached settings singleton and load fresh settings
    get_settings.cache_clear()
    settings = get_settings()

    new_llm = LLMService(
        api_key=settings.gemini_api_key,
        model_name=settings.adk_model_name,
    )
    new_embedding = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        output_dimensionality=settings.embedding_dimensions,
        model_name=settings.embedding_model,
    )

    if app_state is not None:
        app_state.llm_service = new_llm

    if hasattr(ServiceRegistry, "_llm"):
        ServiceRegistry._llm = new_llm
    if hasattr(ServiceRegistry, "llm"):
        ServiceRegistry.llm = new_llm
    if hasattr(ServiceRegistry, "llm_service"):
        ServiceRegistry.llm_service = new_llm

    if hasattr(ServiceRegistry, "_embedding_provider"):
        ServiceRegistry._embedding_provider = new_embedding
    if hasattr(ServiceRegistry, "embedding_provider"):
        ServiceRegistry.embedding_provider = new_embedding

    if getattr(ServiceRegistry, "_initialized", False):
        if hasattr(ServiceRegistry, "_planning_service") and ServiceRegistry._planning_service is not None:
            try:
                ServiceRegistry._planning_service.llm = new_llm
                ServiceRegistry._planning_service._llm = new_llm
            except Exception:
                pass
        if hasattr(ServiceRegistry, "_writing_service") and ServiceRegistry._writing_service is not None:
            try:
                ServiceRegistry._writing_service.llm = new_llm
                ServiceRegistry._writing_service._llm = new_llm
            except Exception:
                pass
        if hasattr(ServiceRegistry, "_paper_retrieval") and ServiceRegistry._paper_retrieval is not None:
            try:
                ServiceRegistry._paper_retrieval._embedding_provider = new_embedding
            except Exception:
                pass

    logger.info(
        "Runtime services reloaded (mode=%s, use_vertex_ai=%s, is_configured=%s)",
        "vertex" if settings.use_vertex_ai else "studio",
        settings.use_vertex_ai,
        new_llm.is_configured,
    )
    return new_llm, new_embedding


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/auth", response_model=AuthStatusResponse)
async def get_auth_status() -> AuthStatusResponse:
    """Get active authentication mode and credential status for popup modal."""
    gemini_key = _get_env_value("GEMINI_API_KEY")
    openalex_key = _get_env_value("OPENALEX_API_KEY")
    openalex_email = _get_env_value("OPENALEX_EMAIL")
    vertex_project = _get_env_value("VERTEX_PROJECT")
    vertex_location = _get_env_value("VERTEX_LOCATION") or "us-central1"
    use_vertex_raw = _get_env_value("USE_VERTEX_AI")

    settings = get_settings()

    if use_vertex_raw.lower() in ("true", "1", "yes"):
        use_vertex = True
    elif use_vertex_raw.lower() in ("false", "0", "no"):
        use_vertex = False
    else:
        use_vertex = settings.use_vertex_ai

    mode: Literal["studio", "vertex"] = "vertex" if use_vertex else "studio"
    has_credentials = (
        _is_real_project(vertex_project) if use_vertex else _is_real_key(gemini_key)
    )

    masked_key = _mask_key(gemini_key)
    masked_openalex = _mask_key(openalex_key)

    return AuthStatusResponse(
        mode=mode,
        has_credentials=has_credentials,
        gemini_api_key_preview=masked_key if _is_real_key(gemini_key) else None,
        gemini_api_key_set=_is_real_key(gemini_key),
        vertex_project=vertex_project if _is_real_project(vertex_project) else None,
        vertex_location=vertex_location,
        use_vertex_ai=use_vertex,
        openalex_api_key_preview=masked_openalex if _is_real_key(openalex_key) else None,
        openalex_api_key_set=_is_real_key(openalex_key),
        openalex_email=openalex_email or "",
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection_endpoint(body: TestConnectionRequest) -> TestConnectionResponse:
    """Perform a live ping to the Gemini model to test credentials before saving."""
    from core.llm.service import LLMService

    settings = get_settings()
    test_model = settings.adk_model_name or "gemini-3.5-flash"

    target_mode: Literal["studio", "vertex"]
    if body.mode:
        target_mode = body.mode
    elif body.gemini_api_key is not None and body.vertex_project is None:
        target_mode = "studio"
    elif body.vertex_project is not None and body.gemini_api_key is None:
        target_mode = "vertex"
    else:
        target_mode = "vertex" if settings.use_vertex_ai else "studio"

    if body.gemini_api_key is not None:
        api_key = body.gemini_api_key.strip()
    else:
        api_key = _get_env_value("GEMINI_API_KEY") or settings.gemini_api_key

    if body.vertex_project is not None:
        project = body.vertex_project.strip()
    else:
        project = _get_env_value("VERTEX_PROJECT") or settings.vertex_project

    if body.vertex_location is not None and body.vertex_location.strip():
        location = body.vertex_location.strip()
    else:
        location = _get_env_value("VERTEX_LOCATION") or settings.vertex_location or "us-central1"

    result = await LLMService.test_connection(
        mode=target_mode,
        api_key=api_key,
        project=project,
        location=location,
        model_name=test_model,
    )

    return TestConnectionResponse(
        success=result["success"],
        message=result["message"],
        model=result.get("model", test_model),
        latency_ms=result.get("latency_ms"),
        mode=target_mode,
        error=result.get("error"),
        details=result.get("details"),
    )

@router.post("/auth", response_model=SettingsResponse)
async def update_auth(body: AuthUpdateRequest, request: Request) -> SettingsResponse:
    """Save auth credentials to .env and immediately hot-reload runtime services."""
    async with _ENV_WRITE_LOCK:
        use_vertex = body.use_vertex_ai if body.use_vertex_ai is not None else (body.mode == "vertex" if body.mode is not None else None)

        updates: dict[str, str] = {}
        if use_vertex is not None:
            updates["USE_VERTEX_AI"] = "true" if use_vertex else "false"
        if body.gemini_api_key is not None:
            _, clean_val = _clean_key_value("GEMINI_API_KEY", body.gemini_api_key)
            updates["GEMINI_API_KEY"] = clean_val
        if body.vertex_project is not None:
            _, clean_val = _clean_key_value("VERTEX_PROJECT", body.vertex_project)
            updates["VERTEX_PROJECT"] = clean_val
        if body.vertex_location is not None:
            _, clean_val = _clean_key_value("VERTEX_LOCATION", body.vertex_location)
            updates["VERTEX_LOCATION"] = clean_val
        if body.openalex_api_key is not None:
            _, clean_val = _clean_key_value("OPENALEX_API_KEY", body.openalex_api_key)
            updates["OPENALEX_API_KEY"] = clean_val
        if body.openalex_email is not None:
            _, clean_val = _clean_key_value("OPENALEX_EMAIL", body.openalex_email)
            updates["OPENALEX_EMAIL"] = clean_val

        try:
            if updates:
                _update_env_file(updates)
            reload_runtime_services(getattr(request.app, "state", None))

            gemini_key = _get_env_value("GEMINI_API_KEY")
            openalex_key = _get_env_value("OPENALEX_API_KEY")
            openalex_email = _get_env_value("OPENALEX_EMAIL")
            vertex_project = _get_env_value("VERTEX_PROJECT")
            vertex_location = _get_env_value("VERTEX_LOCATION") or "us-central1"
            use_vertex_raw = _get_env_value("USE_VERTEX_AI")

            settings = get_settings()
            if use_vertex_raw.lower() in ("true", "1", "yes"):
                active_use_vertex = True
            elif use_vertex_raw.lower() in ("false", "0", "no"):
                active_use_vertex = False
            else:
                active_use_vertex = settings.use_vertex_ai

            has_creds = _is_real_project(vertex_project) if active_use_vertex else _is_real_key(gemini_key)

            return SettingsResponse(
                gemini_api_key_set=_is_real_key(gemini_key),
                gemini_api_key_preview=_mask_key(gemini_key),
                openalex_api_key_set=_is_real_key(openalex_key),
                openalex_api_key_preview=_mask_key(openalex_key),
                openalex_email=openalex_email or "",
                embedding_model=settings.embedding_model,
                embedding_dimensions=settings.embedding_dimensions,
                use_vertex_ai=active_use_vertex,
                mode="vertex" if active_use_vertex else "studio",
                vertex_project=vertex_project if _is_real_project(vertex_project) else None,
                vertex_location=vertex_location,
                has_credentials=has_creds,
            )
        except Exception as exc:
            logger.error("Failed to update auth settings: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write settings: {exc}",
            )


@router.get("/models", response_model=AvailableModelsResponse)
async def list_available_models_endpoint(
    gemini_api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
    vertex_location: Optional[str] = None,
    mode: Optional[str] = None,
) -> AvailableModelsResponse:
    """Fetch live available Gemini models directly from Google API, or return fallback."""
    import httpx
    from google import genai

    settings = get_settings()
    gemini_key = gemini_api_key or _get_env_value("GEMINI_API_KEY") or settings.gemini_api_key
    v_project = vertex_project or _get_env_value("VERTEX_PROJECT") or settings.vertex_project
    v_location = vertex_location or _get_env_value("VERTEX_LOCATION") or settings.vertex_location or "us-central1"
    
    use_vertex_raw = _get_env_value("USE_VERTEX_AI")
    is_vertex = (mode == "vertex") if mode else (
        use_vertex_raw.lower() in ("true", "1", "yes") if use_vertex_raw else settings.use_vertex_ai
    )

    fallback_models = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]

    # Strategy 1: Google AI Studio via direct HTTPS (Fastest & Most Reliable)
    if _is_real_key(gemini_key) and not (is_vertex and _is_real_project(v_project)):
        try:
            async with httpx.AsyncClient(timeout=8.0) as http_client:
                url = "https://generativelanguage.googleapis.com/v1beta/models"
                res = await http_client.get(url, params={"key": gemini_key.strip()})
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    model_details = []
                    for m in data.get("models", []):
                        raw_name = m.get("name", "")
                        clean_name = raw_name.replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])

                        if "generateContent" not in methods:
                            continue
                        
                        # Filter out TTS / audio / vision / robotics preview variants to keep list clean
                        if any(skip in clean_name.lower() for skip in ["tts", "embedding", "transcribe", "robotics", "live", "veo", "lyria"]):
                            continue

                        models.append(clean_name)
                        model_details.append(
                            ModelInfo(
                                name=clean_name,
                                display_name=m.get("displayName", clean_name),
                                description=m.get("description", ""),
                                supported_actions=methods,
                            )
                        )

                    unique_models = list(dict.fromkeys(models))
                    if unique_models:
                        return AvailableModelsResponse(
                            models=unique_models,
                            model_details=model_details,
                            source="google_api",
                            total=len(unique_models),
                        )
        except Exception as exc:
            logger.warning("Direct Google API model fetch failed: %s; trying SDK fallback", exc)

    # Strategy 2: Google GenAI SDK (Vertex AI or Studio fallback)
    try:
        if is_vertex and _is_real_project(v_project):
            client = genai.Client(vertexai=True, project=v_project, location=v_location)
        elif _is_real_key(gemini_key):
            client = genai.Client(api_key=gemini_key.strip(), vertexai=False)
        else:
            return AvailableModelsResponse(
                models=fallback_models,
                source="fallback",
                total=len(fallback_models),
            )

        live_models = []
        model_details = []
        for m in client.models.list():
            raw_name = getattr(m, "name", "")
            clean_name = raw_name.replace("models/", "").replace("publishers/google/models/", "")

            if not clean_name or any(skip in clean_name.lower() for skip in ["tts", "embedding", "transcribe", "robotics", "live", "veo", "lyria", "aqa", "imagen"]):
                continue

            supported = getattr(m, "supported_actions", []) or []
            display = getattr(m, "display_name", clean_name)
            desc = getattr(m, "description", "")

            live_models.append(clean_name)
            model_details.append(
                ModelInfo(
                    name=clean_name,
                    display_name=display,
                    description=desc,
                    supported_actions=list(supported) if supported else [],
                )
            )

        unique_models = list(dict.fromkeys(live_models))
        if not unique_models:
            unique_models = fallback_models

        return AvailableModelsResponse(
            models=unique_models,
            model_details=model_details,
            source="google_api",
            total=len(unique_models),
        )
    except Exception as exc:
        logger.warning("Failed to fetch live models from Google API: %s; using fallback", exc)
        return AvailableModelsResponse(
            models=fallback_models,
            source="fallback",
            total=len(fallback_models),
        )


@router.get("", response_model=SettingsResponse)
async def get_settings_endpoint() -> SettingsResponse:
    """Get current application settings with masked credentials."""
    gemini_key = _get_env_value("GEMINI_API_KEY")
    openalex_key = _get_env_value("OPENALEX_API_KEY")
    openalex_email = _get_env_value("OPENALEX_EMAIL")
    vertex_project = _get_env_value("VERTEX_PROJECT")
    vertex_location = _get_env_value("VERTEX_LOCATION") or "us-central1"
    use_vertex_raw = _get_env_value("USE_VERTEX_AI")

    settings = get_settings()
    if use_vertex_raw.lower() in ("true", "1", "yes"):
        use_vertex = True
    elif use_vertex_raw.lower() in ("false", "0", "no"):
        use_vertex = False
    else:
        use_vertex = settings.use_vertex_ai

    has_creds = _is_real_project(vertex_project) if use_vertex else _is_real_key(gemini_key)
    tier1_model = _get_env_value("ADK_TIER1_MODEL") or settings.adk_tier1_model
    tier2_model = _get_env_value("ADK_TIER2_MODEL") or settings.adk_tier2_model

    return SettingsResponse(
        gemini_api_key_set=_is_real_key(gemini_key),
        gemini_api_key_preview=_mask_key(gemini_key),
        openalex_api_key_set=_is_real_key(openalex_key),
        openalex_api_key_preview=_mask_key(openalex_key),
        openalex_email=openalex_email or "",
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        use_vertex_ai=use_vertex,
        mode="vertex" if use_vertex else "studio",
        vertex_project=vertex_project if _is_real_project(vertex_project) else None,
        vertex_location=vertex_location,
        has_credentials=has_creds,
        adk_tier1_model=tier1_model,
        adk_tier2_model=tier2_model,
    )


@router.put("", response_model=SettingsUpdateResponse)
async def update_settings(body: SettingsUpdateRequest, request: Request) -> SettingsUpdateResponse:
    """Update application settings in .env and hot-reload runtime services."""
    async with _ENV_WRITE_LOCK:
        updates: dict[str, str] = {}
        changes: list[str] = []

        if body.gemini_api_key is not None and body.gemini_api_key.strip():
            _, clean_val = _clean_key_value("GEMINI_API_KEY", body.gemini_api_key)
            updates["GEMINI_API_KEY"] = clean_val
            changes.append("Gemini API key")

        if body.openalex_api_key is not None and body.openalex_api_key.strip():
            _, clean_val = _clean_key_value("OPENALEX_API_KEY", body.openalex_api_key)
            updates["OPENALEX_API_KEY"] = clean_val
            changes.append("OpenAlex API key")

        if body.openalex_email is not None:
            _, clean_val = _clean_key_value("OPENALEX_EMAIL", body.openalex_email)
            updates["OPENALEX_EMAIL"] = clean_val
            changes.append("OpenAlex email")

        if body.mode is not None:
            use_vertex = (body.mode == "vertex")
            updates["USE_VERTEX_AI"] = "true" if use_vertex else "false"
            changes.append(f"Auth mode ({body.mode})")
        elif body.use_vertex_ai is not None:
            updates["USE_VERTEX_AI"] = "true" if body.use_vertex_ai else "false"
            changes.append("Vertex AI mode")

        if body.vertex_project is not None:
            _, clean_val = _clean_key_value("VERTEX_PROJECT", body.vertex_project)
            updates["VERTEX_PROJECT"] = clean_val
            changes.append("Vertex project ID")

        if body.vertex_location is not None:
            _, clean_val = _clean_key_value("VERTEX_LOCATION", body.vertex_location)
            updates["VERTEX_LOCATION"] = clean_val
            changes.append("Vertex location")

        if body.adk_tier1_model is not None and body.adk_tier1_model.strip():
            _, clean_val = _clean_key_value("ADK_TIER1_MODEL", body.adk_tier1_model)
            updates["ADK_TIER1_MODEL"] = clean_val
            updates["ADK_MODEL_NAME"] = clean_val
            changes.append(f"Tier 1 model ({clean_val})")

        if body.adk_tier2_model is not None and body.adk_tier2_model.strip():
            _, clean_val = _clean_key_value("ADK_TIER2_MODEL", body.adk_tier2_model)
            updates["ADK_TIER2_MODEL"] = clean_val
            changes.append(f"Tier 2 model ({clean_val})")

        if not updates:
            return SettingsUpdateResponse(
                success=True,
                message="No changes to apply",
                restart_required=False,
            )

        try:
            _update_env_file(updates)
            reload_runtime_services(getattr(request.app, "state", None))

            logger.info("Settings updated: %s", ", ".join(changes))
            return SettingsUpdateResponse(
                success=True,
                message=f"Updated: {', '.join(changes)}. Applied immediately.",
                restart_required=False,
            )
        except Exception as exc:
            logger.error("Failed to update settings: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write settings: {exc}",
            )

