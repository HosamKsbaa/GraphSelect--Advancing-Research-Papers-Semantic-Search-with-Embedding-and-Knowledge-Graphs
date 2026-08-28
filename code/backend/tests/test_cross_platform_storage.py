"""Tests for cross-platform safe directory and file writing."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.storage_utils import get_safe_project_dir, safe_write_text


def test_get_safe_project_dir_fallback(tmp_path):
    """Test that get_safe_project_dir falls back gracefully if primary directory is unwritable."""
    unwritable = tmp_path / "read_only_dir"
    unwritable.mkdir(parents=True, exist_ok=True)
    os.chmod(str(unwritable), 0o444)

    try:
        # Should gracefully fall back to cwd or system temp
        safe_dir = get_safe_project_dir(
            project_id="test-proj-123",
            subfolder="outlines",
            primary_base=unwritable,
        )
        assert safe_dir.exists()
        test_file = safe_dir / "test.txt"
        test_file.write_text("ok")
        assert test_file.read_text() == "ok"
    finally:
        os.chmod(str(unwritable), 0o777)


def test_safe_write_text_primary_and_fallback(tmp_path):
    """Test safe_write_text successfully writes and falls back on permission error."""
    # 1. Normal write
    target = tmp_path / "normal" / "file.txt"
    written_path, used_fallback = safe_write_text(target, "Hello World")
    assert not used_fallback
    assert written_path.read_text() == "Hello World"

    # 2. Simulated permission error fallback
    with patch("pathlib.Path.write_text", side_effect=[PermissionError("Denied"), None]):
        fallback_path, fallback_used = safe_write_text(target, "Fallback Content")
        assert fallback_used
        assert fallback_path.name == "file.txt"
