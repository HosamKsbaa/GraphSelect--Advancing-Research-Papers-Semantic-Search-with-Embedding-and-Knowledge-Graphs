"""Cross-platform safe filesystem storage utilities for Linux, macOS, and Windows.

Provides multi-tiered directory fallbacks, graceful permission degradation, and
safe file-writing primitives to ensure that permission denials, container root
mismatches, or read-only home directories never crash the application.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_safe_project_dir(
    project_id: str,
    subfolder: str = "",
    primary_base: str | Path = "projects",
) -> Path:
    """Resolve a writable project directory with cross-platform fallback tiers.

    Tiers:
    1. Primary base path (e.g. 'projects' or '~/.alrs/projects')
    2. Local workspace data directory ('./data/projects')
    3. System temporary directory (tempfile.gettempdir() / 'alrs_projects')

    Args:
        project_id: Project UUID string.
        subfolder: Optional subfolder inside project (e.g., 'outlines', 'drafts', 'exports').
        primary_base: Preferred base path.

    Returns:
        A guaranteed writable Path object.
    """
    candidates: list[Path] = [
        Path(primary_base).expanduser(),
        Path.cwd() / "data" / "projects",
        Path(tempfile.gettempdir()) / "alrs_projects",
    ]

    for base in candidates:
        try:
            target = base / project_id / subfolder if subfolder else base / project_id
            target.mkdir(parents=True, exist_ok=True)
            # Verify write test
            test_file = target / ".perm_check.tmp"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return target
        except (PermissionError, OSError) as exc:
            logger.warning(
                "Directory tier '%s' unwritable (%s); falling back to next candidate",
                base,
                exc,
            )

    # Ultimate fallback to system temp directory
    fallback = Path(tempfile.gettempdir()) / "alrs_projects" / project_id / (subfolder or "")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def safe_write_text(
    file_path: Path | str,
    content: str,
    encoding: str = "utf-8",
) -> tuple[Path, bool]:
    """Safely write text to disk with automatic permission and fallback handling.

    Args:
        file_path: Target destination path.
        content: Text content to write.
        encoding: Character encoding (default: utf-8).

    Returns:
        Tuple of (actual_path_written, was_fallback_used).
    """
    target = Path(file_path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)
        return target, False
    except (PermissionError, OSError) as exc:
        logger.warning(
            "Primary write to '%s' failed (%s); writing to temp fallback",
            target,
            exc,
        )
        temp_dir = Path(tempfile.gettempdir()) / "alrs_fallbacks"
        temp_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = temp_dir / target.name
        try:
            fallback_path.write_text(content, encoding=encoding)
            return fallback_path, True
        except Exception as inner_exc:
            logger.error("Temp fallback write failed: %s", inner_exc)
            return target, False
