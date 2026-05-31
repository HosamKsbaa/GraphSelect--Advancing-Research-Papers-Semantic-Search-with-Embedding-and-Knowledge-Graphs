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
from features.settings.models import (
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


# --- Helpers ---

# Sentinel values that ship in the default .env template.
# Any key matching one of these is treated as "not configured".
_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_openalex_api_key_here"}


def _mask_key(key: str) -> str:
    """Return a masked preview of an API key, showing only the last 4 chars.

    Masking strategy:
        - Placeholder / empty → ``"Not set"``
        - Very short key (≤ 4 chars) → ``"****"`` (no chars revealed)
        - Normal key → up to 20 bullet chars (``•``) followed by the
          last 4 characters, e.g. ``••••••••••••efgh``

    The 20-bullet cap prevents the frontend from displaying an
    excessively long masked string for very long keys.

    Args:
        key: Raw API key value read from ``.env``.

    Returns:
        Human-readable masked string safe for display in the UI.
    """
    if not key or key in _PLACEHOLDER_KEYS:
        return "Not set"
    # Keys ≤ 4 chars would be fully exposed — mask them entirely
    if len(key) <= 4:
        return "****"
    # Cap the mask body at 20 bullets so the UI column stays compact
    return "•" * min(len(key) - 4, 20) + key[-4:]


def _is_real_key(key: str) -> bool:
    """Check whether *key* is a genuine API key (not a placeholder).

    Args:
        key: Raw value read from ``.env``.

    Returns:
        ``True`` if the key is non-empty and not in
        :data:`_PLACEHOLDER_KEYS`.
    """
    return bool(key) and key not in _PLACEHOLDER_KEYS


def _read_env_lines() -> list[str]:
    """Read all lines from the ``.env`` file as a list of strings.

    Returns:
        List of raw lines (without trailing newlines).  Returns an
        empty list if the file does not exist so callers never need
        to handle ``FileNotFoundError``.
    """
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _get_env_value(key: str) -> str:
    """Read a specific key's value from the ``.env`` file.

    Performs a case-insensitive scan of the file.  Comment lines
    (starting with ``#``) and lines without an ``=`` delimiter are
    silently skipped.

    Args:
        key: Environment variable name to look up (e.g.
            ``"GEMINI_API_KEY"``).

    Returns:
        The trimmed value string, or ``""`` if the key is absent.
    """
    for line in _read_env_lines():
        stripped = line.strip()
        # Skip comments and lines that aren't key=value pairs
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        # Case-insensitive match so "gemini_api_key" == "GEMINI_API_KEY"
        if k.strip().upper() == key.upper():
            return v.strip()
    return ""


def _update_env_file(updates: dict[str, str]) -> None:
    """Update specific keys in the ``.env`` file, preserving structure.

    Algorithm:
        1. Read every line of the existing file.
        2. For each ``KEY=value`` line whose key matches an entry in
           *updates* (case-insensitive), replace the value in-place.
        3. Comment lines and unrelated keys are copied verbatim.
        4. Any keys in *updates* that were **not** found in the file
           are appended at the end.

    This approach keeps the developer's hand-written comments and
    blank-line grouping intact, which is important because operators
    may customise the ``.env`` file manually.

    Args:
        updates: Mapping of environment variable names to their new
            values (e.g. ``{"GEMINI_API_KEY": "abc123"}``).  Keys
            are matched case-insensitively.

    Raises:
        OSError: If the file cannot be written (permissions, disk
            full, etc.).  Callers should handle this.
    """
    lines = _read_env_lines()
    updated_keys: set[str] = set()  # Track which keys have been replaced
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Preserve comments and non-key-value lines as-is
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        k, _, v = stripped.partition("=")
        key_name = k.strip()

        # Check if this line's key matches any of the requested updates
        if key_name.upper() in {u.upper() for u in updates}:
            # Find the matching update key (case-insensitive lookup)
            for update_key, update_val in updates.items():
                if update_key.upper() == key_name.upper():
                    new_lines.append(f"{key_name}={update_val}")
                    updated_keys.add(update_key.upper())
                    break
        else:
            new_lines.append(line)

    # Append any keys that didn't already exist in the file
    for key, val in updates.items():
        if key.upper() not in updated_keys:
            new_lines.append(f"{key}={val}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# --- Endpoints ---

@router.get("", response_model=SettingsResponse)
async def get_settings_endpoint() -> SettingsResponse:
    """Get current application settings with masked API keys.

    Reads raw key values directly from the ``.env`` file (not from
    the cached ``Settings`` singleton) so the response always
    reflects the latest on-disk state.  Embedding model metadata
    comes from the ``Settings`` object because those values are
    not user-editable at runtime.

    Returns:
        ``SettingsResponse`` with boolean flags indicating whether
        each key is configured, masked key previews safe for UI
        display, and read-only embedding configuration.
    """
    # Read keys directly from .env to reflect unsaved / just-written state
    gemini_key = _get_env_value("GEMINI_API_KEY")
    openalex_key = _get_env_value("OPENALEX_API_KEY")
    openalex_email = _get_env_value("OPENALEX_EMAIL")

    # Read-only embedding config from the cached Settings singleton
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
    """Update application settings in the ``.env`` file.

    Only non-``None``, non-empty fields are written; omitted fields
    are left unchanged.  After a successful write the ``Settings``
    LRU cache is invalidated so the *next* request (via any router)
    picks up the new values without a full server restart, although
    some services may still hold stale references.

    Args:
        body: Partial update payload — each field is optional.
            Empty strings are treated as "no change" for API keys,
            but *are* written for email (allows clearing the value).

    Returns:
        ``SettingsUpdateResponse`` indicating which fields were
        changed and whether a restart is recommended.

    Raises:
        HTTPException 500: If the ``.env`` file cannot be written
            (disk full, permission denied, etc.).
    """
    updates: dict[str, str] = {}
    changes: list[str] = []  # Human-readable list for the response message

    # Only update keys that were explicitly provided and non-empty
    if body.gemini_api_key is not None and body.gemini_api_key.strip():
        updates["GEMINI_API_KEY"] = body.gemini_api_key.strip()
        changes.append("Gemini API key")

    if body.openalex_api_key is not None and body.openalex_api_key.strip():
        updates["OPENALEX_API_KEY"] = body.openalex_api_key.strip()
        changes.append("OpenAlex API key")

    # Email is allowed to be empty (clears the polite-pool identity)
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

        # Invalidate the @lru_cache on get_settings() so the next
        # call re-reads the .env file with the updated values.
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
