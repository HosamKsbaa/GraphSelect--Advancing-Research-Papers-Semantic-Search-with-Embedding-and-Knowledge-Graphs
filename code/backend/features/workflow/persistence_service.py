"""Dual-Layer Persistence Service for ALRS v2 ProjectState (Pure Neo4j & Atomic Disk).

Implements Requirement R5 & Principle A35:
1. Disk persistence: atomic write/load to data/projects/{project_id}/project_state.json
   (using tempfile.mkstemp + os.replace with SHA-256 fingerprinting).
2. Pure Neo4j graph persistence (:ResearchCampaign with checkpoint_sha256).
3. Save state:
   - Updates tool_context.state["project_state"] with serialized dict or model.
   - Atomically writes JSON to disk with SHA-256 fingerprint.
   - Upserts into Neo4j :ResearchCampaign graph container.
4. Load state:
   - Recovers from tool_context.state["project_state"] if present.
   - If absent or corrupt, loads from local disk project_state.json.
   - If absent from disk, recovers from Neo4j graph container and heals disk cache.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore[misc, assignment]

from core.db.neo4j_service import Neo4jService
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

NEO4J_SCHEMA_CYPHER = (
    "CREATE CONSTRAINT campaign_id_unique IF NOT EXISTS "
    "FOR (c:ResearchCampaign) REQUIRE c.campaign_id IS UNIQUE"
)

NEO4J_UPSERT_CYPHER = (
    "MERGE (c:ResearchCampaign {campaign_id: $campaign_id}) "
    "ON CREATE SET c.created_at = datetime() "
    "SET c.name = $name, "
    "    c.topic = $topic, "
    "    c.status = $status, "
    "    c.token_budget = $token_budget, "
    "    c.tokens_used = $tokens_used, "
    "    c.checkpoint_sha256 = $checkpoint_sha256, "
    "    c.state_json = $state_json, "
    "    c.updated_at = datetime()"
)

NEO4J_SELECT_CYPHER = (
    "MATCH (c:ResearchCampaign {campaign_id: $campaign_id}) "
    "RETURN c.state_json AS state, c.checkpoint_sha256 AS sha256"
)

PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")
_UNSET: Any = object()


def validate_project_id(project_id: str) -> str:
    """Validate project_id against path traversal and invalid characters."""
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(f"Invalid project_id: must be non-empty string, got {project_id!r}")
    pid_clean = project_id.strip()
    if not PROJECT_ID_PATTERN.match(pid_clean):
        raise ValueError(
            f"Invalid project_id '{project_id}': must contain only alphanumeric characters, "
            f"hyphens, and underscores, with no path separators."
        )
    return pid_clean


def compute_sha256(content: str) -> str:
    """Compute deterministic SHA-256 fingerprint per Principle A35."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AwaitableProjectState(ProjectState):
    """Subclass of ProjectState that is also directly awaitable."""

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
    """Descriptor enabling a method to be called on instance or class."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            return lambda *args, **kwargs: self.func(owner.get_instance(), *args, **kwargs)
        return lambda *args, **kwargs: self.func(instance, *args, **kwargs)


def _resolve_default_base_dir() -> Path:
    """Determine the canonical project storage directory."""
    backend_root = Path(__file__).resolve().parent.parent.parent
    return backend_root / "data" / "projects"


def _get_running_loop_safe() -> asyncio.AbstractEventLoop | None:
    """Get currently running asyncio loop or return None."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _create_done_future(loop: asyncio.AbstractEventLoop | None) -> Any:
    """Create resolved future if loop is active else return None."""
    if loop is not None and loop.is_running():
        fut = loop.create_future()
        fut.set_result(None)
        return fut
    return None


def create_default_neo4j_service() -> Neo4jService | None:
    """Create default Neo4jService from configuration if available."""
    try:
        from config import get_settings

        settings = get_settings()
        if getattr(settings, "neo4j_uri", None):
            return Neo4jService(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
            )
    except Exception as exc:
        logger.debug("Default Neo4jService initialization deferred: %s", exc)
    return None


create_default_mysql_service = create_default_neo4j_service


class ProjectPersistenceService:
    """Dual-layer persistence (atomic disk + pure Neo4j graph) and ADK context."""

    _instance: ProjectPersistenceService | None = None

    @classmethod
    def get_instance(cls) -> ProjectPersistenceService:
        """Get or create singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: ProjectPersistenceService | None) -> None:
        """Set or override singleton instance for testing."""
        cls._instance = instance

    def __init__(
        self,
        neo4j: Any = _UNSET,
        base_data_dir: Path | str | None = None,
        mysql: Any = _UNSET,
    ) -> None:
        """Initialize persistence service with Neo4j and local disk."""
        target_db = neo4j if neo4j is not _UNSET else mysql
        if target_db is _UNSET:
            self.neo4j = create_default_neo4j_service()
        else:
            self.neo4j = target_db
        self.mysql = self.neo4j
        if base_data_dir is not None:
            self.base_data_dir = Path(base_data_dir).resolve()
        else:
            self.base_data_dir = _resolve_default_base_dir()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def get_state_file_path(self, project_id: str) -> Path:
        """Return canonical disk file path for project with traversal check."""
        clean_id = validate_project_id(str(project_id))
        resolved_base = self.base_data_dir.resolve()
        candidate = (resolved_base / clean_id / "project_state.json").resolve()
        if not candidate.is_relative_to(resolved_base):
            raise ValueError(f"Path traversal detected for project_id: '{project_id}'")
        return candidate

    @staticmethod
    def atomic_write_json(file_path: Path, data_str: str) -> str:
        """Atomically write JSON using tempfile.mkstemp and POSIX os.replace."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        dir_path = str(file_path.parent)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=f"{file_path.name}.tmp.", dir=dir_path
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data_str)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(file_path)
            return compute_sha256(data_str)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
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
            current = None
            if hasattr(state_container, "get"):
                current = state_container.get("project_state")
            target_ps = state if isinstance(current, ProjectState) else dumped
            for k, v in [("project_id", str(state.project_id)), ("project_state", target_ps)]:
                try:
                    state_container[k] = v
                except Exception:
                    pass

    async def _upsert_graph(
        self, project_id: str, name: str, state_json: str, sha256: str
    ) -> None:
        """Upsert project state into Neo4j graph container or adapter."""
        if self.neo4j is None:
            return
        params = {
            "campaign_id": project_id,
            "name": name,
            "topic": name,
            "status": "active",
            "token_budget": 500000,
            "tokens_used": 0,
            "checkpoint_sha256": sha256,
            "state_json": state_json,
        }
        try:
            if isinstance(self.neo4j, Neo4jService):
                await self.neo4j.execute_write(NEO4J_UPSERT_CYPHER, params)
            elif hasattr(self.neo4j, "execute"):
                await self.neo4j.execute(UPSERT_PROJECT_STATE_SQL, (project_id, state_json))
        except Exception as exc:
            logger.warning("Failed to upsert project state to graph for %s: %s", project_id, exc)

    @HybridMethod
    def ensure_schema(self) -> Any:
        """Ensure schema constraint exists in Neo4j."""
        loop = _get_running_loop_safe()
        if self.neo4j is None:
            return _create_done_future(loop)
        if loop is not None and loop.is_running():
            task = loop.create_task(self.ensure_schema_async())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        return asyncio.run(self.ensure_schema_async())

    async def ensure_schema_async(self) -> None:
        """Explicit async version to ensure graph schema."""
        if self.neo4j is None:
            return
        if isinstance(self.neo4j, Neo4jService):
            await self.neo4j.execute_write(NEO4J_SCHEMA_CYPHER)
        elif hasattr(self.neo4j, "execute"):
            await self.neo4j.execute(PROJECT_STATES_DDL)

    async def wait_background_tasks(self, timeout: float | None = 5.0) -> None:
        """Wait for pending background persistence tasks."""
        if not self._background_tasks:
            return
        tasks = list(self._background_tasks)
        try:
            if timeout:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
            else:
                await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for %d persistence tasks", len(tasks))

    @HybridMethod
    def save_state(
        self,
        state: ProjectState,
        tool_context: ToolContext | None = None,
    ) -> Any:
        """Save ProjectState across in-memory context, disk JSON, and Neo4j."""
        project_id = str(state.project_id)
        self._inject_into_tool_context(state, tool_context)
        file_path = self.get_state_file_path(project_id)
        state_json = state.model_dump_json(indent=2)
        sha256 = self.atomic_write_json(file_path, state_json)
        return self._dispatch_async_upsert(project_id, state.name, state_json, sha256)

    def _dispatch_async_upsert(
        self, project_id: str, name: str, state_json: str, sha256: str
    ) -> Any:
        """Dispatch asynchronous upsert to Neo4j in background task or sync."""
        loop = _get_running_loop_safe()
        if self.neo4j is None:
            return _create_done_future(loop)
        if loop is not None and loop.is_running():
            task = loop.create_task(self._upsert_graph(project_id, name, state_json, sha256))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        try:
            return asyncio.run(self._upsert_graph(project_id, name, state_json, sha256))
        except Exception as exc:
            logger.warning("Synchronous Neo4j upsert failed for %s: %s", project_id, exc)
            return None

    async def save_state_async(
        self,
        state: ProjectState,
        tool_context: ToolContext | None = None,
    ) -> None:
        """Explicit async save method that awaits Neo4j upsert completion."""
        project_id = str(state.project_id)
        self._inject_into_tool_context(state, tool_context)
        file_path = self.get_state_file_path(project_id)
        state_json = state.model_dump_json(indent=2)
        sha256 = self.atomic_write_json(file_path, state_json)
        await self._upsert_graph(project_id, state.name, state_json, sha256)

    def _load_from_memory(
        self, pid_str: str, tool_context: ToolContext | None
    ) -> ProjectState | None:
        """Load state from tool context if valid."""
        if tool_context is None:
            return None
        container = getattr(tool_context, "state", None) or (
            tool_context if isinstance(tool_context, dict) else None
        )
        if container is None:
            return None
        raw_mem = container.get("project_state")
        if raw_mem is None:
            return None
        try:
            if isinstance(raw_mem, ProjectState) and str(raw_mem.project_id) == pid_str:
                return raw_mem
            if isinstance(raw_mem, dict):
                mem_pid = str(raw_mem.get("project_id", ""))
                if not mem_pid or mem_pid == pid_str:
                    return ProjectState.model_validate(raw_mem)
        except Exception as exc:
            logger.warning("Corrupt project_state in context: %s", exc)
        return None

    def _load_from_disk(
        self, pid_str: str, tool_context: ToolContext | None
    ) -> ProjectState | None:
        """Load state from local disk candidate paths."""
        paths = [
            self.get_state_file_path(pid_str),
            Path("backend/data/projects") / pid_str / "project_state.json",
            Path("data/projects") / pid_str / "project_state.json",
        ]
        for p in paths:
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8")
                    st = ProjectState.model_validate_json(content)
                    self._inject_into_tool_context(st, tool_context)
                    return st
                except Exception as exc:
                    logger.warning("Corrupt disk state at %s: %s", p, exc)
                    break
        return None

    async def _fetch_and_heal_graph(
        self, pid_str: str, tool_context: ToolContext | None
    ) -> ProjectState:
        """Fetch state from Neo4j and heal local disk cache."""
        if self.neo4j is None:
            raise FileNotFoundError(f"Project state for '{pid_str}' not found on disk or context.")
        raw_state: Any = None
        try:
            if isinstance(self.neo4j, Neo4jService):
                recs = await self.neo4j.execute_read(
                    NEO4J_SELECT_CYPHER, {"campaign_id": pid_str}
                )
                raw_state = recs[0].get("state") if recs else None
            elif hasattr(self.neo4j, "fetch_one"):
                row = await self.neo4j.fetch_one(SELECT_PROJECT_STATE_SQL, (pid_str,))
                raw_state = row.get("state") if row else None
        except Exception as exc:
            raise FileNotFoundError(f"Project '{pid_str}' database error: {exc}") from exc
        if not raw_state:
            raise FileNotFoundError(f"Project '{pid_str}' not found in graph.")
        st = (
            ProjectState.model_validate_json(raw_state)
            if isinstance(raw_state, str)
            else ProjectState.model_validate(raw_state)
        )
        self.atomic_write_json(self.get_state_file_path(pid_str), st.model_dump_json(indent=2))
        self._inject_into_tool_context(st, tool_context)
        return st

    @HybridMethod
    def load_state(
        self,
        project_id: str,
        tool_context: ToolContext | None = None,
    ) -> Any:
        """Load ProjectState: tool_context -> disk -> Neo4j."""
        pid_str = str(project_id)
        mem_state = self._load_from_memory(pid_str, tool_context)
        if mem_state is not None:
            return AwaitableProjectState.model_validate(mem_state.model_dump())
        disk_state = self._load_from_disk(pid_str, tool_context)
        if disk_state is not None:
            return AwaitableProjectState.model_validate(disk_state.model_dump())
        loop = _get_running_loop_safe()
        if loop is not None and loop.is_running():
            return AsyncProjectStateLoader(self._fetch_and_heal_graph(pid_str, tool_context))
        res = asyncio.run(self._fetch_and_heal_graph(pid_str, tool_context))
        return AwaitableProjectState.model_validate(res.model_dump())

    def load_state_sync(
        self,
        project_id: str,
        tool_context: ToolContext | None = None,
    ) -> ProjectState:
        """Synchronous load with fallback to asyncio.run if graph recovery needed."""
        pid_str = str(project_id)
        mem_state = self._load_from_memory(pid_str, tool_context)
        if mem_state is not None:
            return mem_state
        disk_state = self._load_from_disk(pid_str, tool_context)
        if disk_state is not None:
            return disk_state
        loop = _get_running_loop_safe()
        if loop is not None and loop.is_running():
            raise RuntimeError(
                "Cannot call load_state_sync from an active event loop thread "
                "when graph recovery is required. Use 'await load_state(...)' instead."
            )
        return asyncio.run(self._fetch_and_heal_graph(pid_str, tool_context))


__all__ = [
    "AwaitableProjectState",
    "AsyncProjectStateLoader",
    "HybridMethod",
    "PROJECT_ID_PATTERN",
    "PROJECT_STATES_DDL",
    "ProjectPersistenceService",
    "SELECT_PROJECT_STATE_SQL",
    "UPSERT_PROJECT_STATE_SQL",
    "compute_sha256",
    "create_default_mysql_service",
    "create_default_neo4j_service",
    "validate_project_id",
]
