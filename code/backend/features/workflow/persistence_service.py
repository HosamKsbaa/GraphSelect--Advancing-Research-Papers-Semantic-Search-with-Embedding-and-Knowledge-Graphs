"""Dual-Layer Persistence Service for ALRS v2 ProjectState.

Implements Requirement R5:
1. Disk persistence: atomic write/load to backend/data/projects/{project_id}/project_state.json
   (using tempfile + replace to prevent corrupt reads).
2. MySQL persistence: project_states table:
   (project_id VARCHAR(36) PRIMARY KEY, state JSON NOT NULL, version INT DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP).
   Auto-creates table in ensure_schema() using MySQLService.
3. Save state:
   - Updates tool_context.state["project_state"] with serialized dict or model.
   - Atomically writes JSON to disk backend/data/projects/{project_id}/project_state.json.
   - Upserts into MySQL project_states table asynchronously.
4. Load state:
   - Recovers from tool_context.state["project_state"] if present.
   - If absent or corrupt, loads from local disk project_state.json.
   - If absent from disk, recovers from MySQL project_states table.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore[misc, assignment]

from core.db.mysql_service import MySQLService
from features.workflow.state_models import ProjectState

logger = logging.getLogger(__name__)

PROJECT_STATES_DDL = """CREATE TABLE IF NOT EXISTS project_states (
    project_id VARCHAR(36) PRIMARY KEY,
    state JSON NOT NULL,
    version INT DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
)"""

UPSERT_PROJECT_STATE_SQL = """INSERT INTO project_states (project_id, state, version)
VALUES (%s, %s, 1)
ON DUPLICATE KEY UPDATE
    state = VALUES(state),
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP"""

SELECT_PROJECT_STATE_SQL = "SELECT state, version, updated_at FROM project_states WHERE project_id = %s"

PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_project_id(project_id: str) -> str:
    """Validate project_id against path traversal and invalid filesystem characters."""
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(f"Invalid project_id: must be a non-empty string, got {project_id!r}")
    pid_clean = project_id.strip()
    if not PROJECT_ID_PATTERN.match(pid_clean):
        raise ValueError(
            f"Invalid project_id '{project_id}': must contain only alphanumeric characters, "
            f"hyphens, and underscores, with no path separators or traversal characters."
        )
    return pid_clean


class AwaitableProjectState(ProjectState):
    """Subclass of ProjectState that is also directly awaitable.

    Enables both synchronous access (`state = service.load_state(id)`) and
    asynchronous access (`state = await service.load_state(id)`).
    """

    def __await__(self) -> Any:
        async def _resolve() -> ProjectState:
            return self

        return _resolve().__await__()


class AsyncProjectStateLoader:
    """Awaitable wrapper for async state loading operations."""

    def __init__(self, coro: Any) -> None:
        self._coro = coro

    def __await__(self) -> Any:
        return self._coro.__await__()


class HybridMethod:
    """Descriptor enabling a method to be called on either an instance or the class.

    When called on the class (e.g. ProjectPersistenceService.save_state(...)),
    it automatically delegates to the singleton instance returned by
    `ProjectPersistenceService.get_instance()`.
    """

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            return lambda *args, **kwargs: self.func(owner.get_instance(), *args, **kwargs)
        return lambda *args, **kwargs: self.func(instance, *args, **kwargs)


def _resolve_default_base_dir() -> Path:
    """Determine the canonical project storage directory."""
    # Anchored relative to the backend package
    backend_root = Path(__file__).resolve().parent.parent.parent
    return backend_root / "data" / "projects"


def create_default_mysql_service() -> MySQLService | None:
    """Create a default MySQLService from configuration if available."""
    try:
        from config import get_settings

        settings = get_settings()
        if getattr(settings, "mysql_host", None):
            return MySQLService(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                database=settings.mysql_database,
            )
    except Exception as exc:
        logger.debug("Default MySQLService initialization deferred: %s", exc)
    return None


_UNSET: Any = object()


class ProjectPersistenceService:
    """Coordinates dual-layer persistence (disk + MySQL) and ADK tool context integration."""

    _instance: ProjectPersistenceService | None = None

    @classmethod
    def get_instance(cls) -> ProjectPersistenceService:
        """Get or create the singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: ProjectPersistenceService | None) -> None:
        """Set or override the singleton service instance (useful for testing)."""
        cls._instance = instance

    def __init__(
        self,
        mysql: Any = _UNSET,
        base_data_dir: Path | str | None = None,
    ) -> None:
        """Initialize the persistence service.

        Args:
            mysql: Optional MySQLService instance. If omitted, attempts to instantiate from config.
            base_data_dir: Base directory for project data storage.
        """
        if mysql is _UNSET:
            self.mysql = create_default_mysql_service()
        else:
            self.mysql = mysql
        if base_data_dir is not None:
            self.base_data_dir = Path(base_data_dir).resolve()
        else:
            self.base_data_dir = _resolve_default_base_dir()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def get_state_file_path(self, project_id: str) -> Path:
        """Return the canonical disk file path for a project state with path traversal protection."""
        clean_id = validate_project_id(str(project_id))
        resolved_base = self.base_data_dir.resolve()
        candidate = (resolved_base / clean_id / "project_state.json").resolve()
        if not candidate.is_relative_to(resolved_base):
            raise ValueError(f"Path traversal detected for project_id: '{project_id}'")
        return candidate

    @staticmethod
    def atomic_write_json(file_path: Path, data_str: str) -> None:
        """Atomically write JSON data to file using a temporary sibling file and replace."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = file_path.with_name(f"{file_path.name}.tmp.{uuid.uuid4().hex}")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(data_str)
                f.flush()
                os.fsync(f.fileno())
            tmp_file.replace(file_path)
        except Exception:
            if tmp_file.exists():
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass
            raise

    def _inject_into_tool_context(
        self,
        state: ProjectState,
        tool_context: ToolContext | None,
    ) -> None:
        """Helper to inject state into tool_context.state."""
        if tool_context is None:
            return
        state_container = getattr(tool_context, "state", None)
        if state_container is None and isinstance(tool_context, dict):
            state_container = tool_context

        if state_container is not None and hasattr(state_container, "__setitem__"):
            dumped = state.model_dump(mode="json")
            stages_dict = {
                "stage_1_research": dumped.get("stage_1_research", {}),
                "stage_2_analysis": dumped.get("stage_2_analysis", {}),
                "stage_3_planning": dumped.get("stage_3_planning", {}),
                "stage_4_writing": dumped.get("stage_4_writing", {}),
                "stage_5_export": dumped.get("stage_5_export", {}),
            }
            current = None
            if hasattr(state_container, "get"):
                current = state_container.get("project_state")
            target_ps = state if isinstance(current, ProjectState) else dumped

            items_to_set = [
                ("project_id", str(state.project_id)),
                ("project_state", target_ps),
                ("stages", stages_dict),
                ("stage_1_research", stages_dict["stage_1_research"]),
                ("stage_2_analysis", stages_dict["stage_2_analysis"]),
                ("stage_3_planning", stages_dict["stage_3_planning"]),
                ("stage_4_writing", stages_dict["stage_4_writing"]),
                ("stage_5_export", stages_dict["stage_5_export"]),
                ("message_board", dumped.get("message_board", [])),
            ]
            for k, v in items_to_set:
                try:
                    state_container[k] = v
                except Exception:
                    pass

    async def _upsert_mysql(self, project_id: str, state_json: str) -> None:
        """Perform asynchronous upsert into the project_states MySQL table."""
        if self.mysql is None:
            return
        try:
            await self.mysql.execute(UPSERT_PROJECT_STATE_SQL, (project_id, state_json))
            logger.debug("Persisted project state %s to MySQL", project_id)
        except Exception as exc:
            logger.warning("Failed to upsert project state to MySQL for %s: %s", project_id, exc)

    @HybridMethod
    def ensure_schema(self) -> Any:
        """Ensure the project_states table exists in MySQL.

        Can be called synchronously or awaited in async contexts.
        """
        loop: asyncio.AbstractEventLoop | None = None
        if self.mysql is None:
            try:
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                fut.set_result(None)
                return fut
            except RuntimeError:
                return None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            task = loop.create_task(self.mysql.execute(PROJECT_STATES_DDL))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        else:
            return asyncio.run(self.mysql.execute(PROJECT_STATES_DDL))

    async def ensure_schema_async(self) -> None:
        """Explicit async version to ensure project_states schema."""
        if self.mysql is not None:
            await self.mysql.execute(PROJECT_STATES_DDL)

    async def wait_background_tasks(self, timeout: float | None = 5.0) -> None:
        """Wait for all pending background persistence tasks to complete."""
        if not self._background_tasks:
            return
        tasks = list(self._background_tasks)
        if tasks:
            try:
                if timeout:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
                else:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for %d background persistence tasks", len(tasks))

    @HybridMethod
    def save_state(
        self,
        state: ProjectState,
        tool_context: ToolContext | None = None,
    ) -> Any:
        """Save ProjectState across in-memory tool context, disk JSON, and MySQL.

        1. Updates tool_context.state["project_state"] with serialized dict or model.
        2. Atomically writes JSON to disk backend/data/projects/{project_id}/project_state.json.
        3. Upserts into MySQL project_states table asynchronously.

        Returns an awaitable Task/Future if a running loop exists (allowing optional `await`),
        or completes immediately for synchronous callers.
        """
        project_id = str(state.project_id)

        # 1. Ephemeral In-Memory ADK ToolContext
        self._inject_into_tool_context(state, tool_context)

        # 2. Local Disk Layer (Atomic File Write)
        file_path = self.get_state_file_path(project_id)
        state_json = state.model_dump_json(indent=2)
        self.atomic_write_json(file_path, state_json)

        # 3. Relational MySQL Layer (Asynchronous Upsert)
        loop: asyncio.AbstractEventLoop | None = None
        if self.mysql is None:
            try:
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                fut.set_result(None)
                return fut
            except RuntimeError:
                return None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            task = loop.create_task(self._upsert_mysql(project_id, state_json))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        else:
            try:
                return asyncio.run(self._upsert_mysql(project_id, state_json))
            except Exception as exc:
                logger.warning("Synchronous MySQL upsert failed for %s: %s", project_id, exc)
                return None

    async def save_state_async(
        self,
        state: ProjectState,
        tool_context: ToolContext | None = None,
    ) -> None:
        """Explicit async save method that awaits MySQL upsert completion."""
        project_id = str(state.project_id)
        self._inject_into_tool_context(state, tool_context)
        file_path = self.get_state_file_path(project_id)
        state_json = state.model_dump_json(indent=2)
        self.atomic_write_json(file_path, state_json)
        if self.mysql is not None:
            await self._upsert_mysql(project_id, state_json)

    @HybridMethod
    def load_state(
        self,
        project_id: str,
        tool_context: ToolContext | None = None,
    ) -> Any:
        """Load ProjectState adhering to the recovery hierarchy: tool_context -> disk -> MySQL.

        - Recovers from tool_context.state["project_state"] if present and valid.
        - If absent or corrupt, loads from local disk project_state.json.
        - If absent from disk, recovers from MySQL project_states table.
        """
        pid_str = str(project_id)

        # 1. Ephemeral In-Memory Layer (tool_context)
        if tool_context is not None:
            state_container = getattr(tool_context, "state", None)
            if state_container is None and isinstance(tool_context, dict):
                state_container = tool_context

            if state_container is not None:
                raw_mem = state_container.get("project_state")
                if raw_mem is not None:
                    try:
                        if isinstance(raw_mem, ProjectState):
                            if str(raw_mem.project_id) == pid_str:
                                return AwaitableProjectState.model_validate(raw_mem.model_dump())
                        elif isinstance(raw_mem, dict):
                            mem_pid = str(raw_mem.get("project_id", ""))
                            if not mem_pid or mem_pid == pid_str:
                                st = ProjectState.model_validate(raw_mem)
                                return AwaitableProjectState.model_validate(st.model_dump())
                    except Exception as exc:
                        logger.warning("Corrupt project_state in tool_context for %s: %s", pid_str, exc)

        # 2. Local Disk Layer
        candidate_paths = [
            self.get_state_file_path(pid_str),
            Path("backend/data/projects") / pid_str / "project_state.json",
            Path("data/projects") / pid_str / "project_state.json",
        ]
        disk_loaded = False
        for disk_path in candidate_paths:
            if disk_path.exists():
                try:
                    content = disk_path.read_text(encoding="utf-8")
                    st = ProjectState.model_validate_json(content)
                    self._inject_into_tool_context(st, tool_context)
                    return AwaitableProjectState.model_validate(st.model_dump())
                except Exception as exc:
                    logger.warning("Corrupt disk state at %s for %s: %s", disk_path, pid_str, exc)
                    # Proceed to MySQL fallback
                    break

        # 3. Relational MySQL Layer (Fallback)
        async def _fetch_from_mysql() -> ProjectState:
            if self.mysql is None:
                raise FileNotFoundError(
                    f"Project state for '{pid_str}' not found on disk or context, and MySQL service is not available."
                )
            try:
                row = await self.mysql.fetch_one(SELECT_PROJECT_STATE_SQL, (pid_str,))
            except Exception as exc:
                logger.warning("Failed to fetch state from MySQL for %s: %s", pid_str, exc)
                raise FileNotFoundError(
                    f"Project state for '{pid_str}' not found in tool_context, disk, or MySQL (database error: {exc})."
                ) from exc

            if not row or not row.get("state"):
                raise FileNotFoundError(
                    f"Project state for '{pid_str}' not found in tool_context, disk, or MySQL."
                )

            raw_state = row["state"]
            if isinstance(raw_state, str):
                st = ProjectState.model_validate_json(raw_state)
            elif isinstance(raw_state, dict):
                st = ProjectState.model_validate(raw_state)
            else:
                raise ValueError(f"Unexpected state format in MySQL for {pid_str}: {type(raw_state)}")

            # Recover to disk atomically so subsequent loads hit disk cache
            try:
                target_disk = self.get_state_file_path(pid_str)
                self.atomic_write_json(target_disk, st.model_dump_json(indent=2))
            except Exception as exc:
                logger.warning("Failed to cache MySQL recovered state to disk for %s: %s", pid_str, exc)

            # Recover into tool_context
            self._inject_into_tool_context(st, tool_context)
            return AwaitableProjectState.model_validate(st.model_dump())

        loop: asyncio.AbstractEventLoop | None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            return AsyncProjectStateLoader(_fetch_from_mysql())
        else:
            try:
                res = asyncio.run(_fetch_from_mysql())
                return AwaitableProjectState.model_validate(res.model_dump())
            except Exception:
                raise

    def load_state_sync(
        self,
        project_id: str,
        tool_context: ToolContext | None = None,
    ) -> ProjectState:
        """Synchronously load ProjectState (falls back to asyncio.run if MySQL recovery is needed)."""
        pid_str = str(project_id)

        # 1. tool_context
        if tool_context is not None:
            state_container = getattr(tool_context, "state", None)
            if state_container is None and isinstance(tool_context, dict):
                state_container = tool_context
            if state_container is not None:
                raw_mem = state_container.get("project_state")
                if raw_mem is not None:
                    try:
                        if isinstance(raw_mem, ProjectState) and str(raw_mem.project_id) == pid_str:
                            return raw_mem
                        elif isinstance(raw_mem, dict):
                            return ProjectState.model_validate(raw_mem)
                    except Exception as exc:
                        logger.warning("Corrupt project_state in tool_context: %s", exc)

        # 2. Disk
        file_path = self.get_state_file_path(pid_str)
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                st = ProjectState.model_validate_json(content)
                self._inject_into_tool_context(st, tool_context)
                return st
            except Exception as exc:
                logger.warning("Corrupt disk state at %s: %s", file_path, exc)

        # 3. MySQL
        if self.mysql is not None:
            mysql_client = self.mysql

            async def _load_mysql() -> ProjectState:
                row = await mysql_client.fetch_one(SELECT_PROJECT_STATE_SQL, (pid_str,))
                if not row or not row.get("state"):
                    raise FileNotFoundError(f"Project state for '{pid_str}' not found in MySQL.")
                raw = row["state"]
                st = ProjectState.model_validate_json(raw) if isinstance(raw, str) else ProjectState.model_validate(raw)
                self.atomic_write_json(file_path, st.model_dump_json(indent=2))
                self._inject_into_tool_context(st, tool_context)
                return st

            loop: asyncio.AbstractEventLoop | None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                raise RuntimeError(
                    "Cannot call load_state_sync from an active event loop thread "
                    "when MySQL recovery is required. Use 'await load_state(...)' instead."
                )
            else:
                return asyncio.run(_load_mysql())

        raise FileNotFoundError(f"Project state for '{pid_str}' not found in memory, disk, or MySQL.")


__all__ = [
    "AwaitableProjectState",
    "AsyncProjectStateLoader",
    "HybridMethod",
    "PROJECT_ID_PATTERN",
    "PROJECT_STATES_DDL",
    "ProjectPersistenceService",
    "SELECT_PROJECT_STATE_SQL",
    "UPSERT_PROJECT_STATE_SQL",
    "create_default_mysql_service",
    "validate_project_id",
]
