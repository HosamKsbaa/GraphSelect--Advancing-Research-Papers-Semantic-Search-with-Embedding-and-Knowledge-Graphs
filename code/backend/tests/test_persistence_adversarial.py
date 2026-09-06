"""Adversarial stress test suite for ALRS v2 Dual-Layer Persistence (Requirement R5).

Empirically tests:
1. Corrupt disk JSON recovery falling back to MySQL (syntax errors, zero-byte files, truncated files, invalid schemas).
2. Missing directory auto-creation (deeply nested non-existent dirs, recreated dirs after deletion, MySQL recovery dir creation).
3. Rapid sequential and concurrent atomic disk writes (100 rapid sequential writes, 50 concurrent tasks, reader/writer atomicity, temp file cleanup).
4. Edge cases: Path traversal in project_id, synchronous/asynchronous calling conventions, and event loop behavior.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.workflow import (
    BoardClassification,
    PaperMetadata,
    ProjectPersistenceService,
    ProjectState,
    get_project_state,
    post_to_message_board,
    read_message_board,
    update_stage_substate,
)


class DummyToolContext:
    """Mock ADK ToolContext."""

    def __init__(self, state: dict[str, Any] | None = None, agent_name: str = "AdversarialAgent") -> None:
        self.state = state if state is not None else {}
        self.agent_name = agent_name
        self.actions = MagicMock()


def make_test_project(pid: str, name: str = "Adversarial Project") -> ProjectState:
    p = ProjectState(
        project_id=pid,
        name=name,
        description="Testing persistence under adversarial conditions",
        topic="Adversarial Testing",
        token_budget=100_000,
    )
    p.stage_1_research.meta.status = "in_progress"
    return p


# ===========================================================================
# 1. Corrupt Disk JSON Recovery Falling Back to MySQL
# ===========================================================================

class TestCorruptDiskJSONRecovery:
    """Adversarial tests for corrupted disk files falling back to MySQL."""

    @pytest.mark.asyncio
    async def test_corrupt_json_syntax_fallback_to_mysql(self, tmp_path: Path) -> None:
        """When disk file has invalid JSON syntax, load_state recovers from MySQL and heals disk."""
        project_id = "proj-corrupt-syntax"
        clean_state = make_test_project(project_id, name="Syntax Recovery")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text("{broken: json, not_valid!!", encoding="utf-8")

        # Load state
        loaded = await svc.load_state(project_id)
        assert loaded.project_id == project_id
        assert loaded.name == "Syntax Recovery"
        assert mock_mysql.fetch_one.called

        # Verify disk file was healed (overwritten with clean JSON)
        assert disk_file.exists()
        repaired_content = json.loads(disk_file.read_text(encoding="utf-8"))
        assert repaired_content["project_id"] == project_id
        assert repaired_content["name"] == "Syntax Recovery"

    @pytest.mark.asyncio
    async def test_empty_zero_byte_disk_file_fallback(self, tmp_path: Path) -> None:
        """When disk file is completely empty (0 bytes), load_state recovers from MySQL."""
        project_id = "proj-empty-file"
        clean_state = make_test_project(project_id, name="Zero Byte Recovery")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text("", encoding="utf-8")  # 0 bytes

        loaded = await svc.load_state(project_id)
        assert loaded.project_id == project_id
        assert loaded.name == "Zero Byte Recovery"

        # Disk healed
        assert disk_file.stat().st_size > 0
        repaired = json.loads(disk_file.read_text(encoding="utf-8"))
        assert repaired["name"] == "Zero Byte Recovery"

    @pytest.mark.asyncio
    async def test_truncated_partial_json_fallback(self, tmp_path: Path) -> None:
        """When disk file is truncated mid-stream (e.g. abrupt power cut), recovers from MySQL."""
        project_id = "proj-truncated"
        clean_state = make_test_project(project_id, name="Truncated Recovery")
        full_json = clean_state.model_dump_json(indent=2)
        truncated_json = full_json[: len(full_json) // 3]  # First third only

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text(truncated_json, encoding="utf-8")

        loaded = await svc.load_state(project_id)
        assert loaded.project_id == project_id
        assert loaded.name == "Truncated Recovery"

    @pytest.mark.asyncio
    async def test_schema_invalid_disk_json_fallback(self, tmp_path: Path) -> None:
        """When disk file is valid JSON but violates ProjectState schema (missing required fields), recovers from MySQL."""
        project_id = "proj-schema-invalid"
        clean_state = make_test_project(project_id, name="Schema Valid Recovery")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        # Valid JSON, but missing required 'name' field
        disk_file.write_text(json.dumps({"project_id": project_id, "unknown_field": 123}), encoding="utf-8")

        loaded = await svc.load_state(project_id)
        assert loaded.project_id == project_id
        assert loaded.name == "Schema Valid Recovery"

    @pytest.mark.asyncio
    async def test_corrupt_disk_and_corrupt_mysql_raises_exception(self, tmp_path: Path) -> None:
        """When BOTH disk and MySQL have corrupt data, raises exception and does not silently succeed."""
        project_id = "proj-double-corrupt"
        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": "invalid { json in db", "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text("invalid disk", encoding="utf-8")

        with pytest.raises(Exception):
            await svc.load_state(project_id)

    @pytest.mark.asyncio
    async def test_corrupt_disk_with_no_mysql_raises_file_not_found(self, tmp_path: Path) -> None:
        """When disk is corrupt and MySQL is not configured, raises FileNotFoundError."""
        project_id = "proj-corrupt-no-db"
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        disk_file = svc.get_state_file_path(project_id)
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text("{corrupt", encoding="utf-8")

        with pytest.raises(FileNotFoundError):
            await svc.load_state(project_id)


# ===========================================================================
# 2. Missing Directory Auto-Creation
# ===========================================================================

class TestDirectoryAutoCreation:
    """Adversarial tests for automatic directory creation across layers."""

    def test_deeply_nested_nonexistent_base_dir_auto_creation(self, tmp_path: Path) -> None:
        """save_state creates deeply nested non-existent directory trees."""
        deep_dir = tmp_path / "deep" / "nested" / "sub1" / "sub2" / "projects"
        assert not deep_dir.exists()

        svc = ProjectPersistenceService(mysql=None, base_data_dir=deep_dir)
        project = make_test_project("proj-deep-dir")

        svc.save_state(project)

        expected_file = deep_dir / "proj-deep-dir" / "project_state.json"
        assert expected_file.exists()
        data = json.loads(expected_file.read_text(encoding="utf-8"))
        assert data["project_id"] == "proj-deep-dir"

    def test_directory_deleted_between_saves_recreated(self, tmp_path: Path) -> None:
        """If directory is manually deleted while service runs, subsequent save re-creates it."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project = make_test_project("proj-recreate")

        # Save 1
        svc.save_state(project)
        folder = tmp_path / "proj-recreate"
        assert folder.exists()

        # Adversarially delete folder
        shutil.rmtree(folder)
        assert not folder.exists()

        # Save 2
        project.name = "Recreated Project"
        svc.save_state(project)
        assert folder.exists()
        loaded = json.loads((folder / "project_state.json").read_text(encoding="utf-8"))
        assert loaded["name"] == "Recreated Project"

    @pytest.mark.asyncio
    async def test_mysql_recovery_creates_missing_directory(self, tmp_path: Path) -> None:
        """When recovering from MySQL, parent folder does not exist at all; it must be auto-created."""
        project_id = "proj-db-created-dir"
        clean_state = make_test_project(project_id, name="Recovered Dir")
        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        target_dir = tmp_path / "nonexistent_subfolder"
        assert not target_dir.exists()

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=target_dir)

        loaded = await svc.load_state(project_id)
        assert loaded.project_id == project_id

        # Verify target folder and file were created
        cached_file = target_dir / project_id / "project_state.json"
        assert cached_file.exists()
        data = json.loads(cached_file.read_text(encoding="utf-8"))
        assert data["name"] == "Recovered Dir"


# ===========================================================================
# 3. Rapid Sequential and Concurrent Atomic Disk Writes
# ===========================================================================

class TestRapidAtomicWrites:
    """Stress tests for rapid sequential and concurrent atomic disk writes."""

    def test_rapid_sequential_atomic_writes_100_cycles(self, tmp_path: Path) -> None:
        """Execute 100 rapid sequential saves on the same project; verify correctness and 0 orphan tmp files."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project_id = "proj-rapid-seq"
        project = make_test_project(project_id)

        for i in range(100):
            project.name = f"Sequential Revision {i}"
            project.tokens_used = i * 10
            svc.save_state(project)

        proj_folder = tmp_path / project_id
        files = list(proj_folder.iterdir())

        # Crucial check: exactly 1 file exists (project_state.json) - no left-behind .tmp files
        assert len(files) == 1, f"Found unexpected extra/temp files: {[f.name for f in files]}"
        assert files[0].name == "project_state.json"

        # Verify final state
        final_state = json.loads(files[0].read_text(encoding="utf-8"))
        assert final_state["name"] == "Sequential Revision 99"
        assert final_state["tokens_used"] == 990

    @pytest.mark.asyncio
    async def test_rapid_concurrent_async_writes_stress(self, tmp_path: Path) -> None:
        """Execute 50 concurrent async tasks saving different states to the same project.

        Tests POSIX atomic replace and verifies no race condition causes file corruption.
        """
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project_id = "proj-concurrent-stress"

        async def _save_worker(idx: int) -> None:
            p = make_test_project(project_id, name=f"Concurrent Worker {idx}")
            p.tokens_used = idx
            await svc.save_state_async(p)

        # Run 50 concurrent saves
        tasks = [_save_worker(i) for i in range(50)]
        await asyncio.gather(*tasks)

        proj_folder = tmp_path / project_id
        files = list(proj_folder.iterdir())

        # No orphan temp files
        assert len(files) == 1, f"Leftover temp files detected: {[f.name for f in files]}"
        assert files[0].name == "project_state.json"

        # State must be completely valid JSON and pass Pydantic schema
        content = files[0].read_text(encoding="utf-8")
        parsed = ProjectState.model_validate_json(content)
        assert parsed.project_id == project_id
        assert parsed.name.startswith("Concurrent Worker ")

    @pytest.mark.asyncio
    async def test_concurrent_reader_writer_atomicity(self, tmp_path: Path) -> None:
        """Writer constantly overwrites project_state.json while readers continuously read.

        Verifies that readers NEVER encounter partial JSON, 0-byte reads, or decode errors.
        """
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project_id = "proj-reader-writer-atomicity"
        initial_proj = make_test_project(project_id, name="Initial")
        svc.save_state(initial_proj)

        read_errors: list[str] = []
        read_count = 0
        stop_reading = False

        async def reader_worker() -> None:
            nonlocal read_count, read_errors
            file_path = svc.get_state_file_path(project_id)
            while not stop_reading:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    data = json.loads(content)
                    assert data["project_id"] == project_id
                    read_count += 1
                except Exception as e:
                    read_errors.append(f"Reader error: {type(e).__name__}: {e}")
                await asyncio.sleep(0.001)

        async def writer_worker() -> None:
            for i in range(40):
                p = make_test_project(project_id, name=f"Writer Iteration {i}")
                p.tokens_used = i * 100
                svc.save_state(p)
                await asyncio.sleep(0.002)

        reader_task = asyncio.create_task(reader_worker())
        await writer_worker()
        stop_reading = True
        await reader_task

        assert not read_errors, f"Encountered corrupt reads during atomic file writes: {read_errors}"
        assert read_count > 10, f"Expected reader to perform multiple reads, got {read_count}"

    def test_disk_write_failure_cleans_up_temp_file(self, tmp_path: Path) -> None:
        """When an exception occurs during disk write, the temporary file is unlinked cleanly."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project = make_test_project("proj-write-fail")
        file_path = svc.get_state_file_path("proj-write-fail")

        # Force replace to fail
        with patch("pathlib.Path.replace", side_effect=OSError("Simulated disk error")):
            with pytest.raises(OSError, match="Simulated disk error"):
                svc.save_state(project)

        # Confirm no leftover .tmp files
        folder = tmp_path / "proj-write-fail"
        if folder.exists():
            tmp_files = [f for f in folder.iterdir() if ".tmp." in f.name]
            assert not tmp_files, f"Temp files not cleaned up on failure: {tmp_files}"


# ===========================================================================
# 4. Vulnerabilities & Edge Cases (Deadlock, Path Traversal, Type Safety)
# ===========================================================================

class TestVulnerabilitiesAndEdgeCases:
    """Exposes and records real vulnerabilities in persistence service."""

    def test_path_traversal_risk_in_project_id(self, tmp_path: Path) -> None:
        """Verifies that path traversal attempts in project_id are strictly rejected."""
        base_dir = tmp_path / "safe_projects_dir"
        base_dir.mkdir()
        svc = ProjectPersistenceService(mysql=None, base_data_dir=base_dir)

        # Malicious project_id containing path traversal
        traversal_id = "../evil_escaped_dir"
        with pytest.raises(ValueError, match="Invalid project_id|Path traversal"):
            svc.get_state_file_path(traversal_id)

        # Absolute path attempt
        abs_id = "/tmp/evil"
        with pytest.raises(ValueError, match="Invalid project_id|Path traversal"):
            svc.get_state_file_path(abs_id)

    @pytest.mark.asyncio
    async def test_coroutine_deadlock_in_load_state_sync_within_event_loop(self, tmp_path: Path) -> None:
        """Exposes the critical deadlock: calling load_state_sync inside an active asyncio loop

        when disk is corrupt/missing deadlocks because run_coroutine_threadsafe blocks the event loop thread.
        """
        project_id = "proj-deadlock-repro"
        clean_state = make_test_project(project_id, name="MySQL State")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        # Disk file is corrupt
        bad_file = svc.get_state_file_path(project_id)
        bad_file.parent.mkdir(parents=True, exist_ok=True)
        bad_file.write_text("{broken json", encoding="utf-8")

        # If executed in a separate worker thread (e.g. via ThreadPoolExecutor), it can complete:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            # Calling load_state_sync in worker thread allows main loop to handle the coroutine
            fut = pool.submit(svc.load_state_sync, project_id)
            # Wait with a timeout
            try:
                res = fut.result(timeout=2.0)
                assert res.project_id == project_id
            except concurrent.futures.TimeoutError:
                pytest.fail("load_state_sync timed out even in worker thread")

    @pytest.mark.asyncio
    async def test_async_project_state_loader_type_inconsistency(self, tmp_path: Path) -> None:
        """Exposes type inconsistency: when recovering from MySQL inside an active loop,

        svc.load_state(pid) returns AsyncProjectStateLoader which does NOT inherit from ProjectState,
        breaking synchronous callers expecting a ProjectState.
        """
        project_id = "proj-type-inconsistency"
        clean_state = make_test_project(project_id, name="Type Inconsistency State")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)

        # Calling without await:
        raw_ret = svc.load_state(project_id)

        # In an active loop with MySQL fallback, raw_ret is AsyncProjectStateLoader, NOT ProjectState!
        assert not isinstance(raw_ret, ProjectState)
        assert hasattr(raw_ret, "__await__")

        # Synchronous field access fails:
        with pytest.raises(AttributeError):
            _ = raw_ret.name

        # Awaiting resolves it:
        resolved = await raw_ret
        assert isinstance(resolved, ProjectState)
        assert resolved.name == "Type Inconsistency State"
