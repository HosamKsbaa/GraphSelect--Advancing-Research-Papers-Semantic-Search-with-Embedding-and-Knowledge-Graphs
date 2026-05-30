"""FastAPI settings router for ALRS v2 backend.

Exposes endpoints to read and update application configuration (API keys, email)
stored in the .env file. Sensitive values are masked in GET responses.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


# --- Models ---

class SettingsResponse(BaseModel):
    """Current settings (API keys are masked)."""

    gemini_api_key_set: bool = Field(description="Whether a real Gemini API key is configured")
    gemini_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_api_key_set: bool = Field(description="Whether a real OpenAlex API key is configured")
    openalex_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_email: str = Field(description="Email for OpenAlex polite pool")
    embedding_model: str = Field(description="Current embedding model name")
    embedding_dimensions: int = Field(description="Current embedding dimensions")


class SettingsUpdateRequest(BaseModel):
    """Request body for updating settings."""

    gemini_api_key: Optional[str] = Field(None, description="New Gemini API key (leave empty to keep current)")
    openalex_api_key: Optional[str] = Field(None, description="New OpenAlex API key (leave empty to keep current)")
    openalex_email: Optional[str] = Field(None, description="Email for OpenAlex polite pool")


class SettingsUpdateResponse(BaseModel):
    """Response after updating settings."""

    success: bool
    message: str
    restart_required: bool = Field(
        default=True,
        description="Whether a server restart is needed for changes to take effect",
    )


# --- Helpers ---

_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_openalex_api_key_here"}


def _mask_key(key: str) -> str:
    """Return a masked preview of an API key, showing only the last 4 characters."""
    if not key or key in _PLACEHOLDER_KEYS:
        return "Not set"
    if len(key) <= 4:
        return "****"
    return "•" * min(len(key) - 4, 20) + key[-4:]


def _is_real_key(key: str) -> bool:
    """Check if the key is a real key (not a placeholder)."""
    return bool(key) and key not in _PLACEHOLDER_KEYS


def _read_env_lines() -> list[str]:
    """Read the .env file lines."""
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _get_env_value(key: str) -> str:
    """Read a specific key from the .env file."""
    for line in _read_env_lines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip().upper() == key.upper():
            return v.strip()
    return ""


def _update_env_file(updates: dict[str, str]) -> None:
    """Update specific keys in the .env file, preserving comments and structure."""
    lines = _read_env_lines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        k, _, v = stripped.partition("=")
        key_name = k.strip()

        if key_name.upper() in {u.upper() for u in updates}:
            # Find the matching update key
            for update_key, update_val in updates.items():
                if update_key.upper() == key_name.upper():
                    new_lines.append(f"{key_name}={update_val}")
                    updated_keys.add(update_key.upper())
                    break
        else:
            new_lines.append(line)

    # Add any keys that weren't in the file
    for key, val in updates.items():
        if key.upper() not in updated_keys:
            new_lines.append(f"{key}={val}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# --- Endpoints ---

@router.get("", response_model=SettingsResponse)
async def get_settings_endpoint() -> SettingsResponse:
    """Get current application settings with masked API keys."""
    gemini_key = _get_env_value("GEMINI_API_KEY")
    openalex_key = _get_env_value("OPENALEX_API_KEY")
    openalex_email = _get_env_value("OPENALEX_EMAIL")

    settings = get_settings()

    return SettingsResponse(
        gemini_api_key_set=_is_real_key(gemini_key),
        gemini_api_key_preview=_mask_key(gemini_key),
        openalex_api_key_set=_is_real_key(openalex_key),
        openalex_api_key_preview=_mask_key(openalex_key),
        openalex_email=openalex_email or "",
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )


@router.put("", response_model=SettingsUpdateResponse)
async def update_settings(body: SettingsUpdateRequest) -> SettingsUpdateResponse:
    """Update application settings in the .env file.

    Changes are written to the .env file. A server restart is required
    for the changes to take full effect (cached settings singleton).
    """
    updates: dict[str, str] = {}
    changes: list[str] = []

    if body.gemini_api_key is not None and body.gemini_api_key.strip():
        updates["GEMINI_API_KEY"] = body.gemini_api_key.strip()
        changes.append("Gemini API key")

    if body.openalex_api_key is not None and body.openalex_api_key.strip():
        updates["OPENALEX_API_KEY"] = body.openalex_api_key.strip()
        changes.append("OpenAlex API key")

    if body.openalex_email is not None:
        updates["OPENALEX_EMAIL"] = body.openalex_email.strip()
        changes.append("OpenAlex email")

    if not updates:
        return SettingsUpdateResponse(
            success=True,
            message="No changes to apply",
            restart_required=False,
        )

    try:
        _update_env_file(updates)

        # Clear the cached settings so next request picks up new values
        from config import get_settings as _gs
        _gs.cache_clear()

        logger.info("Settings updated: %s", ", ".join(changes))
        return SettingsUpdateResponse(
            success=True,
            message=f"Updated: {', '.join(changes)}. Restart the server for full effect.",
            restart_required=True,
        )
    except Exception as exc:
        logger.error("Failed to update settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write settings: {exc}",
        )
