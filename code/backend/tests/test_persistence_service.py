"""Comprehensive test suite for ProjectPersistenceService and Agent Tool Registration.

Verifies Requirement R5:
1. Disk JSON saving and loading roundtrip with atomic file replacement.
2. MySQL upsert, schema initialization, and recovery.
3. Recovery hierarchy: tool_context -> disk -> MySQL.
4. Tool auto-persistence: post_to_message_board, update_stage_substate, read_message_board.
5. Agent tool registration across ProjectAgent, ResearchAgent, PlannerAgent, WriterAgent.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.agent import (
    ProjectAgent as RootProjectAgent,
    create_root_agent,
    project_agent,
    root_agent,
)
from agents.orchestrator.agent import ProjectAgent, create_orchestrator_agent
from agents.planner.agent import PlannerAgent, create_planner_agent
from agents.research.agent import ResearchAgent, create_research_agent
from agents.writing.agent import WriterAgent, create_writer_agent
from features.workflow import (
    BoardClassification,
    PaperMetadata,
    ProjectPersistenceService,
    ProjectState,
    StageStatus,
    get_project_state,
    post_to_message_board,
    read_message_board,
    update_stage_substate,
)
from features.workflow.persistence_service import (
    PROJECT_STATES_DDL,
    SELECT_PROJECT_STATE_SQL,
    UPSERT_PROJECT_STATE_SQL,
)


class DummyToolContext:
    """Mock ADK ToolContext for test isolation."""

    def __init__(self, state: dict[str, Any] | None = None, agent_name: str = "TestAgent") -> None:
        self.state = state if state is not None else {}
        self.agent_name = agent_name
        self.actions = MagicMock()
        self.actions.escalate = False
        self.actions.skip_summarization = False


def create_sample_project(project_id: str = "proj-test-123", name: str = "Neural Graph Review") -> ProjectState:
    """Helper to generate a rich, populated ProjectState."""
    p = ProjectState(
        project_id=project_id,
        name=name,
        description="Comprehensive literature review on graph transformers.",
        topic="Graph Neural Networks",
        token_budget=500_000,
    )
    # Stage 1 inputs and paper
    p.stage_1_research.meta.status = "in_progress"
    p.stage_1_research.inputs.research_questions = ["How do graph transformers scale?"]
    p.stage_1_research.artifacts.papers["10.1145/sample.doi"] = PaperMetadata(
        doi="10.1145/sample.doi",
        title="Scalable Graph Representation Learning",
        authors=["Alice Smith", "Bob Jones"],
        year=2024,
        citation_count=42,
    )
    # Message board post
    p.post_message(
        author_agent="ResearchAgent",
        message_type="insight",
        title="O(N) Attention in Graph Transformers",
        content="Discovered linear attention mechanism for dense graph structures.",
        tags=["graph", "attention", "efficiency"],
        related_paper_dois=["10.1145/sample.doi"],
    )
    return p


# ===========================================================================
# 1. Disk Persistence & Atomic File Replacement
# ===========================================================================

class TestDiskPersistence:
    """Tests atomic disk saving, loading, and corrupt-file handling."""

    def test_disk_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Verify saving to disk JSON and reading back preserves complete state."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project = create_sample_project("proj-disk-1")

        # Save to disk
        svc.save_state(project)

        expected_file = tmp_path / "proj-disk-1" / "project_state.json"
        assert expected_file.exists(), f"File {expected_file} was not created"

        # Inspect raw JSON content
        raw_json = json.loads(expected_file.read_text(encoding="utf-8"))
        assert raw_json["project_id"] == "proj-disk-1"
        assert raw_json["name"] == "Neural Graph Review"
        assert "10.1145/sample.doi" in raw_json["stage_1_research"]["artifacts"]["papers"]
        assert len(raw_json["message_board"]) == 1

        # Load back
        loaded = svc.load_state("proj-disk-1")
        assert isinstance(loaded, ProjectState)
        assert loaded.project_id == "proj-disk-1"
        assert loaded.name == project.name
        assert loaded.stage_1_research.artifacts.papers["10.1145/sample.doi"].title == "Scalable Graph Representation Learning"
        assert loaded.message_board[0].title == "O(N) Attention in Graph Transformers"

    def test_atomic_file_replacement_leaves_no_temp_files(self, tmp_path: Path) -> None:
        """Verify that atomic write replaces cleanly without leaving temporary files."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project = create_sample_project("proj-atomic")

        svc.save_state(project)
        folder = tmp_path / "proj-atomic"
        files = list(folder.iterdir())
        assert len(files) == 1
        assert files[0].name == "project_state.json"

    def test_corrupt_disk_file_handling_raises_when_no_fallback(self, tmp_path: Path) -> None:
        """Corrupt disk file causes load_state to raise FileNotFoundError when no MySQL fallback exists."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        project_id = "proj-corrupt"
        file_path = tmp_path / project_id / "project_state.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Write corrupted, non-JSON bytes
        file_path.write_text("{broken json invalid syntax ...", encoding="utf-8")

        with pytest.raises(FileNotFoundError):
            svc.load_state(project_id)


# ===========================================================================
# 2. MySQL Upsert, Schema Initialization, and Recovery
# ===========================================================================

class TestMySQLPersistence:
    """Tests MySQL schema initialization, async upsert, and fallback recovery."""

    @pytest.mark.asyncio
    async def test_ensure_schema_executes_ddl(self) -> None:
        """Verify ensure_schema runs the project_states table DDL."""
        mock_mysql = AsyncMock()
        mock_mysql.execute = AsyncMock(return_value=0)
        svc = ProjectPersistenceService(mysql=mock_mysql)

        await svc.ensure_schema()
        mock_mysql.execute.assert_called_once()
        called_ddl = mock_mysql.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS project_states" in called_ddl
        assert "project_id VARCHAR(36) PRIMARY KEY" in called_ddl

    @pytest.mark.asyncio
    async def test_mysql_upsert_on_save_state(self, tmp_path: Path) -> None:
        """Verify save_state issues an UPSERT query to MySQL with serialized JSON."""
        mock_mysql = AsyncMock()
        mock_mysql.execute = AsyncMock(return_value=1)
        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        project = create_sample_project("proj-mysql-upsert")

        # Save state and await MySQL task completion
        await svc.save_state(project)

        assert mock_mysql.execute.called
        query = mock_mysql.execute.call_args[0][0]
        args = mock_mysql.execute.call_args[0][1]
        assert "INSERT INTO project_states" in query
        assert "ON DUPLICATE KEY UPDATE" in query
        assert args[0] == "proj-mysql-upsert"
        # Validate that the serialized string is valid JSON of the state
        parsed = json.loads(args[1])
        assert parsed["project_id"] == "proj-mysql-upsert"

    @pytest.mark.asyncio
    async def test_mysql_recovery_when_disk_missing(self, tmp_path: Path) -> None:
        """When state is not in memory or on disk, recovers from MySQL and caches to disk."""
        project = create_sample_project("proj-recovered")
        state_json = project.model_dump_json(indent=2)

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": state_json, "version": 2})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)

        # Confirm file does not exist initially on disk
        target_file = tmp_path / "proj-recovered" / "project_state.json"
        assert not target_file.exists()

        # Load state
        loaded = await svc.load_state("proj-recovered")
        assert isinstance(loaded, ProjectState)
        assert loaded.project_id == "proj-recovered"
        assert loaded.name == project.name
        assert "10.1145/sample.doi" in loaded.stage_1_research.artifacts.papers

        # Verify it was cached to disk!
        assert target_file.exists()
        cached_json = json.loads(target_file.read_text(encoding="utf-8"))
        assert cached_json["project_id"] == "proj-recovered"

    @pytest.mark.asyncio
    async def test_mysql_recovery_when_disk_corrupted(self, tmp_path: Path) -> None:
        """When disk file is corrupted, recovery falls through to MySQL."""
        project = create_sample_project("proj-corrupt-disk")
        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": project.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        bad_file = tmp_path / "proj-corrupt-disk" / "project_state.json"
        bad_file.parent.mkdir(parents=True, exist_ok=True)
        bad_file.write_text("corrupted bytes", encoding="utf-8")

        loaded = await svc.load_state("proj-corrupt-disk")
        assert loaded.project_id == "proj-corrupt-disk"
        assert mock_mysql.fetch_one.called


# ===========================================================================
# 3. Recovery Hierarchy: tool_context -> disk -> MySQL
# ===========================================================================

class TestRecoveryHierarchy:
    """Tests strict adherence to tool_context -> disk -> MySQL recovery order."""

    @pytest.mark.asyncio
    async def test_tool_context_takes_precedence_over_disk_and_mysql(self, tmp_path: Path) -> None:
        """If tool_context has state, disk and MySQL are NOT queried."""
        mem_proj = create_sample_project("proj-hier", name="Memory Version")
        disk_proj = create_sample_project("proj-hier", name="Disk Version")
        db_proj = create_sample_project("proj-hier", name="DB Version")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": db_proj.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = tmp_path / "proj-hier" / "project_state.json"
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text(disk_proj.model_dump_json(), encoding="utf-8")

        ctx = DummyToolContext(state={"project_state": mem_proj})

        loaded = await svc.load_state("proj-hier", tool_context=ctx)
        assert loaded.name == "Memory Version"
        mock_mysql.fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_disk_takes_precedence_over_mysql_when_context_empty(self, tmp_path: Path) -> None:
        """If tool_context has no state, disk is used and MySQL is NOT queried."""
        disk_proj = create_sample_project("proj-hier2", name="Disk Version")
        db_proj = create_sample_project("proj-hier2", name="DB Version")

        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": db_proj.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        disk_file = tmp_path / "proj-hier2" / "project_state.json"
        disk_file.parent.mkdir(parents=True, exist_ok=True)
        disk_file.write_text(disk_proj.model_dump_json(), encoding="utf-8")

        ctx = DummyToolContext(state={})

        loaded = await svc.load_state("proj-hier2", tool_context=ctx)
        assert loaded.name == "Disk Version"
        # Tool context should be hydrated
        assert ctx.state["project_state"]["name"] == "Disk Version"
        mock_mysql.fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_mysql_used_when_both_context_and_disk_absent(self, tmp_path: Path) -> None:
        """When context and disk are absent, recovers from MySQL and populates both."""
        db_proj = create_sample_project("proj-hier3", name="DB Version")
        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": db_proj.model_dump_json()})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        ctx = DummyToolContext(state={})

        loaded = await svc.load_state("proj-hier3", tool_context=ctx)
        assert loaded.name == "DB Version"
        assert ctx.state["project_state"]["name"] == "DB Version"
        # Disk file created
        disk_file = tmp_path / "proj-hier3" / "project_state.json"
        assert disk_file.exists()


# ===========================================================================
# 4. Tool Auto-Persistence Integration
# ===========================================================================

class TestToolAutoPersistence:
    """Verifies that state_tools automatically trigger dual-layer persistence."""

    @pytest.mark.asyncio
    async def test_post_to_message_board_auto_persists_to_disk(self, tmp_path: Path) -> None:
        """Calling post_to_message_board persists the new message directly to disk JSON."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project = create_sample_project("proj-auto-msg")
        # Save initial state to disk so folder exists
        svc.save_state(project)
        ctx = DummyToolContext(state={"project_state": project}, agent_name="ResearchAgent")

        # Post a serendipitous discovery
        res = await post_to_message_board(
            message_type="serendipity",
            title="Serendipitous Cross-Citation",
            content="Found relevant paper outside primary seed query.",
            stage="stage_1_research",
            tags=["serendipity", "cross-domain"],
            tool_context=ctx,
        )
        assert res["status"] == "success"

        # Check disk file
        disk_file = tmp_path / "proj-auto-msg" / "project_state.json"
        assert disk_file.exists()
        disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
        titles = [m["title"] for m in disk_data["message_board"]]
        assert "Serendipitous Cross-Citation" in titles

    @pytest.mark.asyncio
    async def test_update_stage_substate_auto_persists_to_disk(self, tmp_path: Path) -> None:
        """Calling update_stage_substate updates quadrant and persists to disk JSON."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project = create_sample_project("proj-auto-quad")
        svc.save_state(project)
        ctx = DummyToolContext(state={"project_state": project}, agent_name="ResearchAgent")

        # Update meta quadrant
        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="meta",
            data={"status": "completed", "progress_percentage": 100},
            tool_context=ctx,
        )
        assert res["status"] == "success"

        disk_file = tmp_path / "proj-auto-quad" / "project_state.json"
        disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
        assert disk_data["stage_1_research"]["meta"]["status"] == "completed"
        assert disk_data["stage_1_research"]["meta"]["progress_percentage"] == 100

    @pytest.mark.asyncio
    async def test_read_message_board_with_ack_auto_persists_to_disk(self, tmp_path: Path) -> None:
        """Calling read_message_board with mark_as_acknowledged=True updates and persists."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project = create_sample_project("proj-auto-ack")
        svc.save_state(project)
        ctx = DummyToolContext(state={"project_state": project}, agent_name="PlannerAgent")

        # Message is initially not acknowledged by PlannerAgent
        assert not project.message_board[0].is_acknowledged_by("PlannerAgent")

        # Read with ack
        res = await read_message_board(
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res["status"] == "success"

        # Verify in disk state
        disk_file = tmp_path / "proj-auto-ack" / "project_state.json"
        disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
        acks = disk_data["message_board"][0].get("acknowledged_by") or disk_data["message_board"][0].get("acknowledgments", [])
        assert "PlannerAgent" in acks


# ===========================================================================
# 5. Agent Tool Registration Verification
# ===========================================================================

class TestAgentToolRegistration:
    """Verifies that ProjectAgent, ResearchAgent, PlannerAgent, and WriterAgent register workflow tools."""

    EXPECTED_WORKFLOW_TOOLS = {
        "get_project_state",
        "post_to_message_board",
        "read_message_board",
        "update_stage_substate",
    }

    def _extract_tool_names(self, agent: Any) -> set[str]:
        return {getattr(t, "__name__", str(t)) for t in getattr(agent, "tools", [])}

    def test_project_agent_tool_registration(self) -> None:
        """Verify ProjectAgent has all 4 workflow tools registered."""
        agent = create_orchestrator_agent()
        registered = self._extract_tool_names(agent)
        missing = self.EXPECTED_WORKFLOW_TOOLS - registered
        assert not missing, f"ProjectAgent missing workflow tools: {missing}"
        assert {"create_new_project", "select_project", "list_projects"}.issubset(registered)

    def test_research_agent_tool_registration(self) -> None:
        """Verify ResearchAgent has all 4 workflow tools registered."""
        agent = create_research_agent()
        registered = self._extract_tool_names(agent)
        missing = self.EXPECTED_WORKFLOW_TOOLS - registered
        assert not missing, f"ResearchAgent missing workflow tools: {missing}"
        assert {"add_research_question", "list_research_questions", "get_project_papers"}.issubset(registered)

    def test_planner_agent_tool_registration(self) -> None:
        """Verify PlannerAgent has all 4 workflow tools registered."""
        agent = create_planner_agent()
        registered = self._extract_tool_names(agent)
        missing = self.EXPECTED_WORKFLOW_TOOLS - registered
        assert not missing, f"PlannerAgent missing workflow tools: {missing}"
        assert {"get_project_summary", "get_ranked_papers", "generate_outline"}.issubset(registered)

    def test_writer_agent_tool_registration(self) -> None:
        """Verify WriterAgent has all 4 workflow tools registered."""
        agent = create_writer_agent()
        registered = self._extract_tool_names(agent)
        missing = self.EXPECTED_WORKFLOW_TOOLS - registered
        assert not missing, f"WriterAgent missing workflow tools: {missing}"
        assert {"export_bibtex", "export_latex", "export_citation_graph"}.issubset(registered)

    def test_root_agent_and_package_exports(self) -> None:
        """Verify root_agent in agents.agent exports ProjectAgent and workflow tools."""
        root = create_root_agent()
        registered = self._extract_tool_names(root)
        missing = self.EXPECTED_WORKFLOW_TOOLS - registered
        assert not missing, f"root_agent missing workflow tools: {missing}"
        assert callable(ProjectAgent)
        assert callable(ResearchAgent)
        assert callable(PlannerAgent)
        assert callable(WriterAgent)


# ===========================================================================
# 6. Hybrid & Synchronous/Asynchronous Usage
# ===========================================================================

class TestHybridCallingConventions:
    """Verifies hybrid class/instance calling and sync/async flexibility."""

    def test_hybrid_class_and_instance_save(self, tmp_path: Path) -> None:
        """Calling save_state via class or instance works seamlessly."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        p1 = create_sample_project("proj-hybrid-1")
        p2 = create_sample_project("proj-hybrid-2")

        # Instance call
        svc.save_state(p1)
        assert (tmp_path / "proj-hybrid-1" / "project_state.json").exists()

        # Class call
        ProjectPersistenceService.save_state(p2)
        assert (tmp_path / "proj-hybrid-2" / "project_state.json").exists()

    def test_sync_load_state_sync_method(self, tmp_path: Path) -> None:
        """Synchronously calling load_state_sync loads from disk cleanly."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        p = create_sample_project("proj-sync-load")
        svc.save_state(p)

        loaded = svc.load_state_sync("proj-sync-load")
        assert loaded.project_id == "proj-sync-load"
        assert loaded.name == p.name


class TestRemediationFixes:
    """Tests verifying Milestone 4 remediation fixes (deadlock-free MySQL recovery, background tasks, warning-free schema)."""

    @pytest.mark.asyncio
    async def test_mysql_recovery_in_get_project_state_without_deadlock(self, tmp_path: Path) -> None:
        """Verifies that get_project_state recovers from MySQL when cold on disk without event loop deadlock."""
        project_id = "proj-no-deadlock"
        clean_state = create_sample_project(project_id, name="Recovered MySQL State")
        mock_mysql = AsyncMock()
        mock_mysql.fetch_one = AsyncMock(return_value={"state": clean_state.model_dump_json(), "version": 1})

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        ctx = {"project_id": project_id}
        res = await asyncio.wait_for(get_project_state(tool_context=ctx), timeout=2.0)
        assert res.get("status") == "success"
        assert res["data"]["project_id"] == project_id
        assert res["data"]["name"] == "Recovered MySQL State"

    @pytest.mark.asyncio
    async def test_save_state_background_tasks_retention(self, tmp_path: Path) -> None:
        """Verifies that save_state retains a strong reference in _background_tasks until completed."""
        mock_mysql = AsyncMock()
        mock_mysql.execute = AsyncMock(return_value=1)
        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        project = create_sample_project("proj-bg-task", name="BG Task Test")

        task = svc.save_state(project)
        assert task in svc._background_tasks
        await task
        assert task not in svc._background_tasks

    def test_ensure_schema_clean_no_unawaited_warning(self) -> None:
        """Verifies that ensure_schema with mysql=None returns None and emits no RuntimeWarning."""
        import warnings
        svc = ProjectPersistenceService(mysql=None)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            res = svc.ensure_schema()
            assert res is None

    @pytest.mark.asyncio
    async def test_wait_background_tasks(self, tmp_path: Path) -> None:
        """Verifies that wait_background_tasks awaits all pending persistence tasks."""
        mock_mysql = AsyncMock()
        mock_mysql.execute = AsyncMock(return_value=1)
        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
        project = create_sample_project("proj-wait-bg", name="Wait BG Test")

        svc.save_state(project)
        assert len(svc._background_tasks) > 0
        await svc.wait_background_tasks(timeout=2.0)
        assert len(svc._background_tasks) == 0
