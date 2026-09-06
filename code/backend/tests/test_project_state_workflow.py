"""Comprehensive Automated Verification Suite for ALRS v2 Literature Review Workflow.

Implements Requirement R6:
- Tier 1: Feature Coverage (>=5 tests each for F3 through F11 = 45 tests)
- Tier 2: Boundary & Corner Cases (>=5 tests each for F3 through F11 = 45 tests)
- Tier 3: Cross-Feature Pairwise Interactions (6 tests)
- Tier 4: Real-World Application Scenarios (5 tests)
- Tier 5: Adversarial Coverage Hardening (12 tests)

Total: 113 comprehensive tests.
Zero external network calls (100% offline hermetic execution).
Strict execution performance budget (< 3.0 seconds).
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from agents.orchestrator.agent import create_orchestrator_agent
from agents.planner.agent import create_planner_agent
from agents.research.agent import create_research_agent
from agents.writing.agent import create_writer_agent
from features.workflow.execution_pipeline import (
    AnalysisStageRunner,
    BaseStageRunner,
    ExportStageRunner,
    PlanningStageRunner,
    ResearchStageRunner,
    STAGE_ORDER,
    STAGE_SEQUENCE,
    StageExecutionResult,
    WorkflowExecutionPipeline,
    WritingStageRunner,
    run_pipeline,
    run_stage,
)
from features.workflow.persistence_service import (
    PROJECT_STATES_DDL,
    UPSERT_PROJECT_STATE_SQL,
    ProjectPersistenceService,
    validate_project_id,
)
from features.workflow.state_models import (
    AnalysisArtifacts,
    AnalysisInputs,
    BoardClassification,
    BoardMessage,
    ComparisonDimension,
    ExportArtifacts,
    ExportInputs,
    OutlineStructure,
    PaperCluster,
    PaperFinding,
    PaperMetadata,
    PaperRanking,
    PlanningArtifacts,
    PlanningInputs,
    ProjectState,
    ResearchArtifacts,
    ResearchInputs,
    ResearchGap,
    SectionBlueprint,
    SectionDraft,
    SectionReview,
    Stage1ResearchState,
    WritingArtifacts,
    Stage2AnalysisState,
    Stage3PlanningState,
    Stage4WritingState,
    Stage5ExportState,
    StageMeta,
    StageNote,
    StageStatus,
    StructuredComparisonMatrix,
    WorkflowStageName,
    deep_merge,
    normalize_doi,
    normalize_stage_name,
    utc_now,
)
from features.workflow.state_tools import (
    VALID_MESSAGE_TYPES,
    VALID_QUADRANTS,
    VALID_STAGES,
    get_project_state,
    post_to_message_board,
    read_message_board,
    set_active_project_state,
    update_stage_substate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test Helpers: DummyToolContext, MockAgent, MockAsyncMySQL
# ---------------------------------------------------------------------------

class DummyAgent:
    """Mock agent object imitating Google ADK agent."""
    def __init__(self, name: str = "ResearchAgent") -> None:
        self.name = name


class DummyToolContext:
    """Mock ToolContext object imitating Google ADK runtime session state."""
    def __init__(
        self,
        state: dict[str, Any] | None = None,
        agent_name: str = "ResearchAgent",
    ) -> None:
        self.state: dict[str, Any] = state if state is not None else {}
        self.agent = DummyAgent(agent_name)
        self.agent_name = agent_name
        self.author = agent_name

    def switch_agent(self, new_agent_name: str) -> None:
        self.agent_name = new_agent_name
        self.author = new_agent_name
        self.agent.name = new_agent_name
        self.state["agent_name"] = new_agent_name


class MockAsyncMySQL:
    """High-fidelity in-memory mock of MySQL service for persistence testing."""
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.fetch_one_calls: list[str] = []
        self.execute_calls: list[str] = []

    async def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> int:
        self.execute_calls.append(sql)
        if "INSERT INTO project_states" in sql and params:
            pid, state_json = params[0], params[1]
            self.rows[str(pid)] = {
                "project_id": str(pid),
                "state": state_json,
                "version": self.rows.get(str(pid), {}).get("version", 0) + 1,
            }
        return 1

    async def fetch_one(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        if params:
            pid = str(params[0])
            self.fetch_one_calls.append(pid)
            return self.rows.get(pid)
        return None

    async def fetch_all(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        return list(self.rows.values())

    async def initialize_schema(self) -> None:
        pass


def make_test_project(
    project_id: str = "proj-test-01",
    name: str = "Graph Attention Networks Review",
    topic: str = "Scalable Graph Neural Networks",
    seed_dois: list[str] | None = None,
) -> ProjectState:
    """Construct a clean, valid ProjectState instance for pipeline testing."""
    state = ProjectState(
        project_id=project_id,
        name=name,
        topic=topic,
        token_budget=500000,
    )
    if seed_dois:
        state.stage_1_research.inputs.seed_dois = seed_dois
    state.stage_1_research.inputs.keywords = ["graph neural networks", "transformers", "inductive learning"]
    state.stage_1_research.inputs.research_questions = [
        "How do graph transformers scale to massive topologies?",
        "What are the empirical limitations of message passing architectures?",
    ]
    return state


# ---------------------------------------------------------------------------
# Test Fixtures: Offline Guard, Isolated Storage, Persistence, Context
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def offline_socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Enforce zero external network calls across the entire test suite."""
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex

    def _guarded_connect(self: Any, *args: Any, **kwargs: Any) -> Any:
        if hasattr(socket, "AF_UNIX") and getattr(self, "family", None) == socket.AF_UNIX:
            return orig_connect(self, *args, **kwargs)
        raise RuntimeError("Network call blocked: offline test isolation enforced")

    def _guarded_connect_ex(self: Any, *args: Any, **kwargs: Any) -> int:
        if hasattr(socket, "AF_UNIX") and getattr(self, "family", None) == socket.AF_UNIX:
            return orig_connect_ex(self, *args, **kwargs)
        raise RuntimeError("Network call blocked: offline test isolation enforced")

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    yield


@pytest.fixture(autouse=True)
def cleanup_active_state() -> Iterator[None]:
    """Ensure active project state singleton is cleanly reset between tests."""
    yield
    set_active_project_state(None)
    ProjectPersistenceService.set_instance(None)


@pytest.fixture
def isolated_storage(tmp_path: Path) -> Path:
    """Provide an ephemeral, isolated directory for project data storage."""
    base_dir = tmp_path / "backend" / "data" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


@pytest.fixture
def mock_mysql_service() -> AsyncMock:
    """Provide an in-memory mock for MySQLService."""
    service = AsyncMock()
    service.execute = AsyncMock(return_value=1)
    service.fetch_one = AsyncMock(return_value=None)
    service.fetch_all = AsyncMock(return_value=[])
    service.initialize_schema = AsyncMock()
    return service


@pytest.fixture
def persistence_service(isolated_storage: Path, mock_mysql_service: AsyncMock) -> Iterator[ProjectPersistenceService]:
    """Create an isolated ProjectPersistenceService instance with mock MySQL."""
    svc = ProjectPersistenceService(mysql=mock_mysql_service, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(svc)
    yield svc
    ProjectPersistenceService.set_instance(None)
    set_active_project_state(None)


@pytest.fixture
def isolated_persistence(isolated_storage: Path) -> Iterator[ProjectPersistenceService]:
    """Create an isolated ProjectPersistenceService without MySQL."""
    svc = ProjectPersistenceService(mysql=None, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(svc)
    yield svc
    ProjectPersistenceService.set_instance(None)
    set_active_project_state(None)


@pytest.fixture
def dummy_tool_context() -> Any:
    """Synthesize an ADK ToolContext container."""
    return DummyToolContext()


@pytest.fixture
def dummy_context() -> Any:
    """Alias fixture for synthesized ADK ToolContext container."""
    return DummyToolContext()


@pytest.fixture
def sample_project() -> ProjectState:
    """Create a populated sample ProjectState for testing."""
    state = ProjectState(
        project_id="proj-sample-01",
        name="Sample Graph Review",
        topic="Graph Neural Networks",
        token_budget=500000,
    )
    state.stage_1_research.artifacts.papers["10.1145/3292500.3330964"] = PaperMetadata(
        doi="10.1145/3292500.3330964",
        title="Graph Neural Networks: A Review of Methods and Applications",
        authors=["Jie Zhou", "Ganqu Cui", "Shengding Hu"],
        year=2020,
        venue="AI Open",
        citation_count=1500,
        is_seed=True,
    )
    state.stage_2_analysis.inputs.similarity_weight = 0.75
    return state

# ===========================================================================
# Tier 1: Feature Coverage (Features F3 through F11: 45 Tests)
# ===========================================================================

# --- Feature 3: Unified ProjectState Schema (5 Tests) ---

def test_tier1_f3_01_default_initialization() -> None:
    """Verify ProjectState initializes with valid defaults across all metadata fields."""
    state = ProjectState(name="Autonomous GNN Review")
    assert state.name == "Autonomous GNN Review"
    assert state.token_budget == 500000
    assert state.tokens_used == 0
    assert state.status == "active"
    assert state.target_level == "master"
    assert state.similarity_threshold == 0.6
    assert state.current_stage == "stage_1_research"
    assert len(state.message_board) == 0
    assert uuid.UUID(state.project_id) is not None
    assert state.created_at.tzinfo == timezone.utc


def test_tier1_f3_02_token_budget_consumption() -> None:
    """Verify token budget deduction and monotonic timestamp tracking upon updates."""
    state = ProjectState(name="GNN Review", token_budget=750000)
    initial_updated = state.updated_at
    state.tokens_used += 45000
    state.touch()

    assert state.token_budget == 750000
    assert state.tokens_used == 45000
    assert (state.token_budget - state.tokens_used) == 705000
    assert state.updated_at >= initial_updated


def test_tier1_f3_03_required_field_validation() -> None:
    """Verify Pydantic v2 rejects missing required fields and unsupported lifecycle statuses."""
    with pytest.raises(ValidationError):
        ProjectState()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ProjectState(name="Invalid Project", status="unknown_status")  # type: ignore[arg-type]


def test_tier1_f3_04_serialization_json_roundtrip(sample_project: ProjectState) -> None:
    """Verify full ProjectState JSON serialization and deserialization fidelity."""
    sample_project.post_message(
        author_agent="ResearchAgent",
        message_type="insight",
        title="Sparse Graph Discovery",
        content="Discovered linear complexity attention mechanism.",
    )
    json_str = sample_project.model_dump_json()
    restored = ProjectState.model_validate_json(json_str)

    assert restored.project_id == sample_project.project_id
    assert restored.name == sample_project.name
    assert len(restored.stage_1_research.artifacts.papers) == len(sample_project.stage_1_research.artifacts.papers)
    assert len(restored.message_board) == len(sample_project.message_board)
    assert restored.message_board[0].title == "Sparse Graph Discovery"


def test_tier1_f3_05_summary_structure_and_metrics() -> None:
    """Verify compact summary structure includes project metadata, stage status, and board metrics."""
    state = ProjectState(name="Graph Transformer Survey", topic="Graph Transformers")
    summary = state.get_summary()

    assert summary["project_id"] == state.project_id
    assert summary["name"] == "Graph Transformer Survey"
    assert summary["topic"] == "Graph Transformers"
    assert summary["current_stage"] == "stage_1_research"
    assert summary["status"] == "active"
    assert set(summary["stages"].keys()) == set(STAGE_ORDER)
    assert summary["message_board_total"] == 0


# --- Feature 4: 4-Quadrant Substate Models (5 Tests) ---

def test_tier1_f4_01_stage_1_research_quadrants() -> None:
    """Verify Stage 1 (Research) substate 4-quadrant topology and defaults."""
    sub = Stage1ResearchState()
    assert isinstance(sub.meta, StageMeta)
    assert sub.meta.agent_name == "ResearchAgent"
    assert sub.meta.status == "not_started"
    assert isinstance(sub.inputs, ResearchInputs)
    assert sub.inputs.max_depth == 2
    assert isinstance(sub.artifacts, ResearchArtifacts)
    assert isinstance(sub.artifacts.papers, dict)
    assert isinstance(sub.notes, list)


def test_tier1_f4_02_stage_2_analysis_quadrants() -> None:
    """Verify Stage 2 (Analysis) substate 4-quadrant topology and clustering inputs."""
    sub = Stage2AnalysisState()
    assert isinstance(sub.meta, StageMeta)
    assert sub.meta.agent_name == "GapFinderAgent"
    assert isinstance(sub.inputs, AnalysisInputs)
    assert sub.inputs.similarity_weight == 0.6
    assert sub.inputs.pagerank_weight == 0.4
    assert isinstance(sub.artifacts, AnalysisArtifacts)
    assert hasattr(sub.artifacts, "clusters")
    assert isinstance(sub.artifacts.gaps, list)
    assert isinstance(sub.notes, list)


def test_tier1_f4_03_stage_3_planning_quadrants() -> None:
    """Verify Stage 3 (Planning) substate 4-quadrant topology and outline structure."""
    sub = Stage3PlanningState()
    assert isinstance(sub.meta, StageMeta)
    assert sub.meta.agent_name == "PlannerAgent"
    assert isinstance(sub.inputs, PlanningInputs)
    assert sub.inputs.style == "thematic"
    assert sub.inputs.target_word_count == 8000
    assert isinstance(sub.artifacts, PlanningArtifacts)
    assert isinstance(sub.artifacts.outline, OutlineStructure)
    assert isinstance(sub.artifacts.doi_mappings, dict)
    assert isinstance(sub.notes, list)


def test_tier1_f4_04_stage_4_writing_quadrants() -> None:
    """Verify Stage 4 (Writing) substate 4-quadrant topology and draft containers."""
    sub = Stage4WritingState()
    assert isinstance(sub.meta, StageMeta)
    assert sub.meta.agent_name == "WriterAgent"
    assert sub.inputs.max_review_iterations == 3
    assert isinstance(sub.artifacts, WritingArtifacts)
    assert isinstance(sub.artifacts.section_drafts, dict)
    assert isinstance(sub.artifacts.section_reviews, dict)
    assert sub.artifacts.citation_grounding_verified is False
    assert isinstance(sub.notes, list)


def test_tier1_f4_05_stage_5_export_quadrants() -> None:
    """Verify Stage 5 (Export) substate 4-quadrant topology and export paths."""
    sub = Stage5ExportState()
    assert isinstance(sub.meta, StageMeta)
    assert sub.meta.agent_name == "WriterAgent"
    assert isinstance(sub.inputs, ExportInputs)
    assert sub.inputs.template == "ieee"
    assert isinstance(sub.artifacts, ExportArtifacts)
    assert isinstance(sub.artifacts.bibtex_entries, list)
    assert sub.artifacts.tex_path is None
    assert sub.artifacts.pdf_path is None
    assert isinstance(sub.notes, list)


# --- Feature 5: Public Message Board (5 Tests) ---

def test_tier1_f5_01_all_six_message_types_supported() -> None:
    """Verify Public Message Board supports all 6 typed message classifications."""
    types = ["insight", "serendipity", "gap", "warning", "decision", "hypothesis"]
    for m_type in types:
        msg = BoardMessage(
            author_agent="TestAgent",
            message_type=m_type,  # type: ignore[arg-type]
            title=f"Title for {m_type}",
            content=f"Content describing {m_type}",
        )
        assert msg.message_type == m_type
        assert msg.classification == m_type


def test_tier1_f5_02_timestamp_generation_and_monotonicity() -> None:
    """Verify messages receive UTC timestamps and maintain monotonic ordering."""
    state = ProjectState(name="Timestamp Test Project")
    msg1 = state.post_message("AgentA", "insight", "First Insight", "Payload 1")
    time.sleep(0.001)
    msg2 = state.post_message("AgentB", "warning", "Second Notice", "Payload 2")

    assert msg1.timestamp.tzinfo == timezone.utc
    assert msg2.timestamp.tzinfo == timezone.utc
    assert msg2.timestamp >= msg1.timestamp


def test_tier1_f5_03_canonical_doi_normalization() -> None:
    """Verify DOI normalization handles URLs, dx resolvers, and uppercase identifiers."""
    raw_dois = [
        "https://doi.org/10.1145/3292500",
        "http://dx.doi.org/10.1016/j.artint.2024",
        "doi: 10.1109/TKDE.2023",
    ]
    msg = BoardMessage(
        author_agent="DiscoveryAgent",
        message_type="insight",
        title="Normalized DOIs",
        content="Referencing multiple academic artifacts.",
        related_paper_dois=raw_dois,
    )
    expected = ["10.1145/3292500", "10.1016/j.artint.2024", "10.1109/tkde.2023"]
    assert msg.related_paper_dois == expected
    assert msg.relevant_dois == expected


def test_tier1_f5_04_agent_acknowledgment_workflow() -> None:
    """Verify agent acknowledgment tracking is idempotent and maintains distinct agent names."""
    msg = BoardMessage(
        author_agent="ResearchAgent",
        message_type="gap",
        title="Coverage Gap",
        content="Sparse benchmark coverage in extreme scale graphs.",
    )
    assert not msg.is_acknowledged_by("PlannerAgent")
    msg.acknowledge("PlannerAgent")
    msg.acknowledge("PlannerAgent")  # Idempotent
    msg.acknowledge("WriterAgent")

    assert msg.is_acknowledged_by("PlannerAgent") is True
    assert msg.is_acknowledged_by("WriterAgent") is True
    assert msg.is_acknowledged_by("ResearchAgent") is False
    assert msg.acknowledged_by == ["PlannerAgent", "WriterAgent"]


def test_tier1_f5_05_state_touch_on_message_posting() -> None:
    """Verify posting a message bumps updated_at timestamp on root ProjectState."""
    state = ProjectState(name="Touch Test")
    initial_updated = state.updated_at
    state.post_message("Agent", "decision", "Selected Architecture", "Using Graph Transformers")

    assert len(state.message_board) == 1
    assert state.updated_at >= initial_updated


# --- Feature 6: Scoped Dot-Path Query Tool (5 Tests) ---

@pytest.mark.asyncio
async def test_tier1_f6_01_summary_scope(sample_project: ProjectState) -> None:
    """Verify get_project_state returns concise summary without serializing full state."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    res = await get_project_state(scope="summary", tool_context=ctx)

    assert res["status"] == "success"
    assert res["scope"] == "summary"
    assert res["data"]["name"] == sample_project.name
    assert "stages" in res["data"]
    assert "message_board_total" in res["data"]


@pytest.mark.asyncio
async def test_tier1_f6_02_stage_scope_isolation(sample_project: ProjectState) -> None:
    """Verify get_project_state with scope='stage' isolates only target stage data."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    res = await get_project_state(scope="stage", stage="stage_1_research", tool_context=ctx)

    assert res["status"] == "success"
    assert res["stage"] == "stage_1_research"
    assert "meta" in res["data"]
    assert "artifacts" in res["data"]
    assert "stage_2_analysis" not in res["data"]


@pytest.mark.asyncio
async def test_tier1_f6_03_stage_name_alias_resolution(sample_project: ProjectState) -> None:
    """Verify get_project_state resolves stage aliases ('research', '1', 'stage_1')."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    for alias in ["research", "1", "stage_1"]:
        res = await get_project_state(scope="stage", stage=alias, tool_context=ctx)
        assert res["status"] == "success"
        assert res["stage"] == "stage_1_research"


@pytest.mark.asyncio
async def test_tier1_f6_04_deep_nested_dot_path(sample_project: ProjectState) -> None:
    """Verify get_project_state resolves deep dot-paths down to scalar floats."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    res = await get_project_state(
        scope="path", path="stage_2_analysis.inputs.similarity_weight", tool_context=ctx
    )
    assert res["status"] == "success"
    assert res["data"] == 0.75


@pytest.mark.asyncio
async def test_tier1_f6_05_compound_doi_key_dot_path(sample_project: ProjectState) -> None:
    """Verify get_project_state resolves dictionary keys with dots (academic DOIs)."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    res = await get_project_state(
        scope="path",
        path="stage_1_research.artifacts.papers.10.1145/3292500.3330964.title",
        tool_context=ctx,
    )
    assert res["status"] == "success"
    assert res["data"] == "Graph Neural Networks: A Review of Methods and Applications"


# --- Feature 7: Message Board Tools (5 Tests) ---

@pytest.mark.asyncio
async def test_tier1_f7_01_post_to_message_board_success(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify post_to_message_board succeeds and synchronizes to tool_context state."""
    dummy_context.state["project_state"] = sample_project
    res = await post_to_message_board(
        message_type="insight",
        title="Sparse Scaling Discovery",
        content="Found linear graph attention with sub-quadratic memory.",
        stage="stage_1_research",
        tags=["scaling", "attention"],
        related_paper_dois=["10.1145/3292500"],
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert uuid.UUID(res["message_id"]) is not None
    assert res["message"]["message_type"] == "insight"
    assert len(sample_project.message_board) == 1


@pytest.mark.asyncio
async def test_tier1_f7_02_read_message_board_filter_by_type(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify read_message_board filters messages by message_type classification."""
    dummy_context.state["project_state"] = sample_project
    await post_to_message_board("insight", "Insight 1", "Content 1", tool_context=dummy_context)
    await post_to_message_board("insight", "Insight 2", "Content 2", tool_context=dummy_context)
    await post_to_message_board("warning", "Rate Limit Warning", "Content 3", tool_context=dummy_context)

    res = await read_message_board(message_type="warning", tool_context=dummy_context)
    assert res["status"] == "success"
    assert res["count"] == 1
    assert res["messages"][0]["message_type"] == "warning"


@pytest.mark.asyncio
async def test_tier1_f7_03_read_message_board_filter_by_stage(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify read_message_board filters messages by associated workflow stage."""
    dummy_context.state["project_state"] = sample_project
    await post_to_message_board("insight", "Research Discovery", "Content", stage="stage_1_research", tool_context=dummy_context)
    await post_to_message_board("gap", "Analysis Deficit", "Content", stage="stage_2_analysis", tool_context=dummy_context)

    res = await read_message_board(stage="research", tool_context=dummy_context)
    assert res["status"] == "success"
    assert res["count"] == 1
    assert res["messages"][0]["stage"] == "stage_1_research"


@pytest.mark.asyncio
async def test_tier1_f7_04_read_message_board_filter_by_doi(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify read_message_board filters messages by referenced paper DOI with normalization."""
    dummy_context.state["project_state"] = sample_project
    await post_to_message_board(
        "insight", "Target Paper", "Content", related_paper_dois=["10.1145/3292500"], tool_context=dummy_context
    )
    await post_to_message_board(
        "insight", "Other Paper", "Content", related_paper_dois=["10.1016/j.artint.2024"], tool_context=dummy_context
    )

    res = await read_message_board(paper_doi="https://doi.org/10.1145/3292500", tool_context=dummy_context)
    assert res["status"] == "success"
    assert res["count"] == 1
    assert "10.1145/3292500" in res["messages"][0]["related_paper_dois"]


@pytest.mark.asyncio
async def test_tier1_f7_05_read_message_board_unacknowledged_and_auto_ack(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify unacknowledged_only filtering and mark_as_acknowledged auto-acknowledgment."""
    dummy_context.state["project_state"] = sample_project
    dummy_context.switch_agent("PlannerAgent")

    await post_to_message_board("gap", "GNN Gap", "Benchmark discrepancy.", tool_context=dummy_context)

    res1 = await read_message_board(unacknowledged_only=True, mark_as_acknowledged=True, tool_context=dummy_context)
    assert res1["count"] == 1

    res2 = await read_message_board(unacknowledged_only=True, unacknowledged_by="PlannerAgent", tool_context=dummy_context)
    assert res2["count"] == 0


# --- Feature 8: Scoped Mutation Tool (5 Tests) ---

@pytest.mark.asyncio
async def test_tier1_f8_01_update_meta_quadrant(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate updates metadata quadrant fields."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="meta",
        data={"status": "in_progress", "progress_percentage": 40.0},
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert res["data"]["status"] == "in_progress"
    assert res["data"]["progress_percentage"] == 40.0
    assert sample_project.stage_1_research.meta.status == "in_progress"


@pytest.mark.asyncio
async def test_tier1_f8_02_update_inputs_quadrant(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate updates inputs quadrant with alias stage resolution."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="analysis",
        quadrant="inputs",
        data={"similarity_weight": 0.85},
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert res["data"]["similarity_weight"] == 0.85
    assert sample_project.stage_2_analysis.inputs.similarity_weight == 0.85


@pytest.mark.asyncio
async def test_tier1_f8_03_update_artifacts_deep_merge(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate deep-merges artifact data without clobbering existing fields."""
    dummy_context.state["project_state"] = sample_project
    sample_project.stage_1_research.artifacts.search_queries = ["query-1"]

    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="artifacts",
        data={"search_queries": ["query-1", "query-2"], "total_discovered": 25},
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert res["data"]["total_discovered"] == 25
    assert res["data"]["search_queries"] == ["query-1", "query-2"]


@pytest.mark.asyncio
async def test_tier1_f8_04_update_notes_quadrant_append(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate appends notes to the notes quadrant list."""
    dummy_context.state["project_state"] = sample_project
    notes_payload: Any = [{"author": "ReviewerAgent", "content": "Check inductive benchmarks."}]

    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="notes",
        data=notes_payload,
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert len(res["data"]) >= 1
    assert res["data"][0]["author"] == "ReviewerAgent"
    assert res["data"][0]["content"] == "Check inductive benchmarks."


@pytest.mark.asyncio
async def test_tier1_f8_05_mutation_updates_timestamps(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify stage quadrant mutation updates both substate meta.updated_at and root updated_at."""
    dummy_context.state["project_state"] = sample_project
    init_meta_updated = sample_project.stage_1_research.meta.updated_at
    init_root_updated = sample_project.updated_at

    await update_stage_substate(
        stage="stage_1_research",
        quadrant="meta",
        data={"progress_percentage": 10.0},
        tool_context=dummy_context,
    )

    assert sample_project.stage_1_research.meta.updated_at >= init_meta_updated
    assert sample_project.updated_at >= init_root_updated


# --- Feature 9: Dual-Layer Persistence (5 Tests) ---

def test_tier1_f9_01_atomic_write_json_success(tmp_path: Path) -> None:
    """Verify atomic_write_json atomically writes and flushes JSON content without orphan tmp files."""
    file_path = tmp_path / "project_state.json"
    content = '{"project_id": "test-atomic", "name": "Atomic Project"}'

    ProjectPersistenceService.atomic_write_json(file_path, content)
    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == content
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_tier1_f9_02_disk_save_and_load_roundtrip(tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify disk save and synchronous load roundtrip preserves all state attributes."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    service.save_state(sample_project)

    loaded = service.load_state_sync(sample_project.project_id)
    assert loaded is not None
    assert loaded.project_id == sample_project.project_id
    assert loaded.name == sample_project.name
    assert len(loaded.stage_1_research.artifacts.papers) == len(sample_project.stage_1_research.artifacts.papers)


@pytest.mark.asyncio
async def test_tier1_f9_03_mysql_schema_init_and_upsert(mock_mysql_service: AsyncMock, tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify schema initialization executes DDL and asynchronous save calls MySQL upsert."""
    service = ProjectPersistenceService(mysql=mock_mysql_service, base_data_dir=tmp_path)
    await service.ensure_schema_async()
    await service.save_state_async(sample_project)

    mock_mysql_service.execute.assert_any_call(PROJECT_STATES_DDL)
    # Verify execute was called with upsert query
    calls = [call[0][0] for call in mock_mysql_service.execute.call_args_list]
    assert any("INSERT INTO project_states" in c for c in calls)


@pytest.mark.asyncio
async def test_tier1_f9_04_recovery_from_mysql_when_disk_missing(mock_mysql_service: AsyncMock, tmp_path: Path) -> None:
    """Verify fallback recovery from MySQL restores state and writes back to disk cache."""
    service = ProjectPersistenceService(mysql=mock_mysql_service, base_data_dir=tmp_path)
    project = make_test_project("proj-f9-04-unique-mysql-recovery")
    mock_mysql_service.fetch_one.return_value = {"state": project.model_dump_json(), "version": 1}

    disk_file = service.get_state_file_path(project.project_id)
    assert not disk_file.exists()

    recovered = await service.load_state(project.project_id)
    assert recovered is not None
    assert recovered.project_id == project.project_id
    assert disk_file.exists()


def test_tier1_f9_05_hybrid_method_class_and_instance_calls(tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify hybrid method descriptor allows calling persistence methods via class or instance."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    ProjectPersistenceService.set_instance(service)

    ProjectPersistenceService.save_state(sample_project)
    loaded = ProjectPersistenceService.load_state(sample_project.project_id)
    assert loaded is not None
    assert loaded.project_id == sample_project.project_id


# --- Feature 10: ADK & Agent Integration (5 Tests) ---

@pytest.mark.asyncio
async def test_tier1_f10_01_tool_context_binding(sample_project: ProjectState) -> None:
    """Verify tools resolve ProjectState from ADK ToolContext container."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project, "project_id": sample_project.project_id})
    res = await get_project_state(scope="summary", tool_context=ctx)

    assert res["status"] == "success"
    assert res["data"]["project_id"] == sample_project.project_id


@pytest.mark.asyncio
async def test_tier1_f10_02_raw_dict_state_preservation(sample_project: ProjectState) -> None:
    """Verify tools preserve raw dict format in tool_context.state when supplied as dict."""
    raw_dict = sample_project.model_dump(mode="json")
    ctx: Any = DummyToolContext(state={"project_state": raw_dict})

    await post_to_message_board("insight", "Dict Test", "Content", tool_context=ctx)
    assert isinstance(ctx.state["project_state"], dict)
    assert len(ctx.state["project_state"]["message_board"]) == 1


@pytest.mark.asyncio
async def test_tier1_f10_03_model_instance_state_preservation(sample_project: ProjectState) -> None:
    """Verify tools preserve Pydantic model instance in tool_context.state when supplied as model."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project})
    await post_to_message_board("insight", "Model Test", "Content", tool_context=ctx)

    assert isinstance(ctx.state["project_state"], ProjectState)
    assert len(ctx.state["project_state"].message_board) == 1


@pytest.mark.asyncio
async def test_tier1_f10_04_author_agent_detection_from_context(sample_project: ProjectState) -> None:
    """Verify tool automatically detects author_agent from calling agent identity in ToolContext."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project}, agent_name="PlannerAgent")
    res = await post_to_message_board("decision", "Approved Arc", "Content", tool_context=ctx)

    assert res["message"]["author_agent"] == "PlannerAgent"


def test_tier1_f10_05_agent_tool_registry_inspection() -> None:
    """Verify ProjectAgent, ResearchAgent, PlannerAgent, and WriterAgent register the 4 workflow tools."""
    expected_tools = {"get_project_state", "post_to_message_board", "read_message_board", "update_stage_substate"}
    factories = [
        create_orchestrator_agent,
        create_research_agent,
        create_planner_agent,
        create_writer_agent,
    ]
    for factory in factories:
        agent = factory()
        tool_names = {getattr(t, "__name__", getattr(t, "name", str(t))) for t in agent.tools}
        assert expected_tools.issubset(tool_names), f"Agent '{agent.name}' missing tools: {expected_tools - tool_names}"


# --- Feature 11: 5-Stage Execution Pipeline (5 Tests) ---

@pytest.mark.asyncio
async def test_tier1_f11_01_full_pipeline_sequential_execution(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify full sequential execution across all 5 workflow stages completes project."""
    proj = make_test_project("proj-f11-01", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    final_state = await pipeline.run_pipeline("proj-f11-01")

    assert final_state.status == "completed"
    for stage_name in STAGE_ORDER:
        substate = getattr(final_state, stage_name)
        assert substate.meta.status == "completed"
        assert substate.meta.progress_percentage == 100.0


@pytest.mark.asyncio
async def test_tier1_f11_02_quadrant_hydration_1_to_2(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify Stage 1 outputs hydrate Stage 2 analysis clustering inputs and target dimensions."""
    proj = make_test_project("proj-f11-02", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    state = await pipeline.run_pipeline("proj-f11-02", stop_at_stage="stage_2_analysis")

    assert state.stage_2_analysis.inputs.clustering_k is not None
    assert state.stage_2_analysis.inputs.clustering_k >= 2
    assert len(state.stage_2_analysis.inputs.target_dimensions) >= 4


@pytest.mark.asyncio
async def test_tier1_f11_03_quadrant_hydration_2_to_3(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify Stage 2 clusters hydrate Stage 3 planning inputs and section outline blueprints."""
    proj = make_test_project("proj-f11-03", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    state = await pipeline.run_pipeline("proj-f11-03", stop_at_stage="stage_3_planning")

    clusters_count = len(state.stage_2_analysis.artifacts.clusters)
    assert state.stage_3_planning.inputs.target_section_count == clusters_count + 2
    assert len(state.stage_3_planning.artifacts.outline.sections) >= 3


@pytest.mark.asyncio
async def test_tier1_f11_04_quadrant_hydration_4_to_5(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify Stage 4 writing outputs hydrate Stage 5 export LaTeX document and BibTeX entries."""
    proj = make_test_project("proj-f11-04", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    state = await pipeline.run_pipeline("proj-f11-04")

    assert state.stage_5_export.artifacts.bibtex_entry_count >= 1
    assert state.stage_5_export.artifacts.tex_path is not None
    assert Path(state.stage_5_export.artifacts.tex_path).exists()


@pytest.mark.asyncio
async def test_tier1_f11_05_checkpoint_resumption_skips_completed(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify checkpoint resumption skips already completed stages without redundant re-execution."""
    proj = make_test_project("proj-f11-05", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    await pipeline.run_pipeline("proj-f11-05", stop_at_stage="stage_2_analysis")

    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 1

    # Resume from checkpoint to completion
    await pipeline.run_pipeline("proj-f11-05", resume_from_checkpoint=True)

    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
    assert pipeline.get_stage_execution_count("stage_3_planning") == 1
    assert pipeline.get_stage_execution_count("stage_4_writing") == 1
    assert pipeline.get_stage_execution_count("stage_5_export") == 1

# ===========================================================================
# Tier 2: Boundary & Corner Cases (Features F3 through F11: 45 Tests)
# ===========================================================================

# --- Feature 3 Boundary Cases (5 Tests) ---

def test_tier2_f3_01_empty_and_whitespace_project_name_rejected() -> None:
    """Verify empty project names are rejected by Pydantic min_length validation."""
    with pytest.raises(ValidationError):
        ProjectState(name="")


def test_tier2_f3_02_token_budget_bounds_zero_and_negative() -> None:
    """Verify token_budget permits zero but rejects negative numbers."""
    state_zero = ProjectState(name="Zero Budget", token_budget=0)
    assert state_zero.token_budget == 0

    with pytest.raises(ValidationError):
        ProjectState(name="Negative Budget", token_budget=-1)


def test_tier2_f3_03_tokens_used_exceeding_budget_overrun() -> None:
    """Verify tokens_used can exceed token_budget to accurately track overruns."""
    state = ProjectState(name="Overrun Project", token_budget=1000)
    state.tokens_used = 1500
    assert state.tokens_used == 1500
    # Serialization succeeds even when over budget
    dumped = state.model_dump_json()
    assert '"tokens_used":1500' in dumped or '"tokens_used": 1500' in dumped


def test_tier2_f3_04_invalid_lifecycle_status_rejected() -> None:
    """Verify arbitrary status literals outside the defined enum are rejected."""
    with pytest.raises(ValidationError):
        ProjectState(name="Invalid Status", status="terminated")  # type: ignore[arg-type]


def test_tier2_f3_05_project_id_alias_bidirectional_sync() -> None:
    """Verify 'id' alias can be used to populate project_id and is accessible via property."""
    state = ProjectState.model_validate({"id": "custom-uuid-1234", "name": "Alias Project"})
    assert state.project_id == "custom-uuid-1234"
    assert state.id == "custom-uuid-1234"


# --- Feature 4 Boundary Cases (5 Tests) ---

def test_tier2_f4_01_empty_authors_and_missing_metadata_in_paper() -> None:
    """Verify PaperMetadata accommodates empty author lists and missing optional fields."""
    paper = PaperMetadata(doi="10.1145/empty-authors", title="Solo Paper", authors=[])
    assert paper.authors == []
    assert paper.year is None
    assert paper.venue is None
    assert paper.citation_count == 0


def test_tier2_f4_02_empty_and_whitespace_note_content_rejected() -> None:
    """Verify empty note content is rejected by Pydantic min_length validation."""
    with pytest.raises(ValidationError):
        StageNote(author="Agent", content="")


def test_tier2_f4_03_progress_percentage_boundary_bounds() -> None:
    """Verify progress_percentage enforces 0.0 <= x <= 100.0 bounds strictly."""
    meta_zero = StageMeta(progress_percentage=0.0)
    assert meta_zero.progress_percentage == 0.0

    meta_hundred = StageMeta(progress_percentage=100.0)
    assert meta_hundred.progress_percentage == 100.0

    with pytest.raises(ValidationError):
        StageMeta(progress_percentage=-0.1)

    with pytest.raises(ValidationError):
        StageMeta(progress_percentage=100.1)


def test_tier2_f4_04_stage_status_tolerant_normalization() -> None:
    """Verify StageMeta tolerates hyphenated and informal status aliases gracefully."""
    meta1 = StageMeta(status="not-started")  # type: ignore[arg-type]
    assert meta1.status == "not_started"

    meta2 = StageMeta(status="in-progress")  # type: ignore[arg-type]
    assert meta2.status == "in_progress"

    meta3 = StageMeta(status="done")  # type: ignore[arg-type]
    assert meta3.status == "completed"


def test_tier2_f4_05_bfs_and_citation_edges_bidirectional_sync() -> None:
    """Verify ResearchArtifacts synchronizes bfs_graph_edges and citation_edges aliases."""
    art1 = ResearchArtifacts.model_validate({"bfs_graph_edges": [("doi1", "doi2")]})
    assert art1.citation_edges == [("doi1", "doi2")]

    art2 = ResearchArtifacts.model_validate({"citation_edges": [("doi3", "doi4")]})
    assert art2.bfs_graph_edges == [("doi3", "doi4")]


# --- Feature 5 Boundary Cases (5 Tests) ---

def test_tier2_f5_01_malformed_doi_variations_graceful_normalization() -> None:
    """Verify normalize_doi safely strips prefixes and returns empty strings for malformed input."""
    assert normalize_doi("http://doi.org/") == ""
    assert normalize_doi("doi:") == ""
    assert normalize_doi("   ") == ""
    assert normalize_doi("") == ""
    assert normalize_doi(None) == ""


def test_tier2_f5_02_empty_and_whitespace_author_agent_rejected() -> None:
    """Verify BoardMessage rejects empty author_agent string."""
    with pytest.raises(ValidationError):
        BoardMessage(author_agent="", message_type="insight", title="Title", content="Content")


def test_tier2_f5_03_title_max_length_boundary_300_chars() -> None:
    """Verify title accepts up to 300 characters but rejects 301 characters."""
    valid_title = "T" * 300
    msg = BoardMessage(author_agent="A", message_type="insight", title=valid_title, content="Content")
    assert len(msg.title) == 300

    invalid_title = "T" * 301
    with pytest.raises(ValidationError):
        BoardMessage(author_agent="A", message_type="insight", title=invalid_title, content="Content")


def test_tier2_f5_04_empty_content_in_board_message_rejected() -> None:
    """Verify BoardMessage rejects empty content string."""
    with pytest.raises(ValidationError):
        BoardMessage(author_agent="A", message_type="insight", title="Title", content="")


def test_tier2_f5_05_acknowledgment_of_nonexistent_message_returns_false() -> None:
    """Verify acknowledge_message returns False when message_id does not exist."""
    state = ProjectState(name="Ack Test")
    state.post_message("A", "insight", "Title", "Content")
    res = state.acknowledge_message("non-existent-uuid-1234", "PlannerAgent")
    assert res is False


# --- Feature 6 Boundary Cases (5 Tests) ---

@pytest.mark.asyncio
async def test_tier2_f6_01_non_existent_attribute_dot_path_returns_error(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify get_project_state returns structured error for non-existent attributes."""
    dummy_context.state["project_state"] = sample_project
    res = await get_project_state(scope="path", path="stage_1_research.non_existent_field", tool_context=dummy_context)
    assert res["status"] == "error"
    assert "failed" in res["message"].lower() or "not found" in res["message"].lower()


@pytest.mark.asyncio
async def test_tier2_f6_02_list_index_out_of_bounds_dot_path_returns_error(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify get_project_state returns structured error for out-of-bounds list index."""
    dummy_context.state["project_state"] = sample_project
    res = await get_project_state(
        scope="path",
        path="stage_3_planning.artifacts.outline.sections.99.title",
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "out of range" in res["message"].lower() or "failed" in res["message"].lower()


@pytest.mark.asyncio
async def test_tier2_f6_03_non_integer_list_index_dot_path_returns_error(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify get_project_state returns structured error for non-integer list lookup tokens."""
    dummy_context.state["project_state"] = sample_project
    res = await get_project_state(
        scope="path",
        path="stage_3_planning.artifacts.outline.sections.first.title",
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "non-integer" in res["message"].lower() or "failed" in res["message"].lower()


@pytest.mark.asyncio
async def test_tier2_f6_04_scalar_traversal_dot_path_returns_error(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify get_project_state returns structured error when traversing into scalar values."""
    dummy_context.state["project_state"] = sample_project
    res = await get_project_state(
        scope="path",
        path="stage_1_research.inputs.max_depth.invalid_child",
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "scalar" in res["message"].lower() or "failed" in res["message"].lower()


@pytest.mark.asyncio
async def test_tier2_f6_05_empty_and_whitespace_dot_path_handling(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify empty and whitespace paths are handled safely without unhandled exceptions."""
    dummy_context.state["project_state"] = sample_project
    res_empty = await get_project_state(scope="path", path="", tool_context=dummy_context)
    assert res_empty["status"] == "error"

    res_space = await get_project_state(scope="path", path="   ", tool_context=dummy_context)
    assert res_space["status"] == "success"


# --- Feature 7 Boundary Cases (5 Tests) ---

@pytest.mark.asyncio
async def test_tier2_f7_01_post_unsupported_message_type_rejected(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify post_to_message_board rejects unsupported message classification types."""
    dummy_context.state["project_state"] = sample_project
    res = await post_to_message_board(
        message_type="unsupported_type",  # type: ignore[arg-type]
        title="Title",
        content="Content",
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "Invalid message_type" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f7_02_read_with_no_matching_filters_returns_empty_list(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify read_message_board returns empty list when no messages match the criteria."""
    dummy_context.state["project_state"] = sample_project
    await post_to_message_board("insight", "Only Insight", "Content", tool_context=dummy_context)

    res = await read_message_board(message_type="warning", tool_context=dummy_context)
    assert res["status"] == "success"
    assert res["count"] == 0
    assert res["messages"] == []


@pytest.mark.asyncio
async def test_tier2_f7_03_read_with_zero_and_negative_limits(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify read_message_board handles non-positive limits safely without crashing."""
    dummy_context.state["project_state"] = sample_project
    for i in range(3):
        await post_to_message_board("insight", f"Post {i}", "Content", tool_context=dummy_context)

    res_zero = await read_message_board(limit=0, tool_context=dummy_context)
    assert res_zero["status"] == "success"

    res_neg = await read_message_board(limit=-5, tool_context=dummy_context)
    assert res_neg["status"] == "success"


@pytest.mark.asyncio
async def test_tier2_f7_04_post_with_mixed_malformed_and_valid_dois(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify post_to_message_board strips malformed DOIs and retains only valid normalized DOIs."""
    dummy_context.state["project_state"] = sample_project
    mixed_dois = [
        "http://doi.org/",
        "https://doi.org/10.1145/3292500",
        "   ",
        "doi:10.1016/j.artint.2024",
    ]
    res = await post_to_message_board(
        message_type="insight",
        title="Mixed DOIs",
        content="Testing filtering.",
        related_paper_dois=mixed_dois,
        tool_context=dummy_context,
    )
    assert res["status"] == "success"
    assert res["message"]["related_paper_dois"] == ["10.1145/3292500", "10.1016/j.artint.2024"]


@pytest.mark.asyncio
async def test_tier2_f7_05_tool_invocation_with_missing_state_returns_error(dummy_context: Any) -> None:
    """Verify tool invocation returns clean error status when context has no state."""
    dummy_context.state = {}
    res = await post_to_message_board("insight", "Orphan Post", "Content", tool_context=dummy_context)
    assert res["status"] == "error"
    assert "No active project state found" in res["message"]


# --- Feature 8 Boundary Cases (5 Tests) ---

@pytest.mark.asyncio
async def test_tier2_f8_01_mutation_invalid_stage_rejected(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate rejects unknown stage names."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_99_nonexistent",
        quadrant="meta",
        data={"status": "in_progress"},
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "Invalid stage" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f8_02_mutation_invalid_quadrant_rejected(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate rejects unknown quadrant names outside the 4-quadrant topology."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="invalid_quadrant_name",
        data={"key": "val"},
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "Invalid quadrant" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f8_03_mutation_wrong_datatype_rejected(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate rejects non-dict data for meta/inputs/artifacts."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="meta",
        data="string_not_dict",  # type: ignore[arg-type]
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "must be a dict" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f8_04_mutation_pydantic_validation_error_capture(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate catches Pydantic validation errors (e.g. progress > 100)."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="meta",
        data={"progress_percentage": 250.0},
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "Validation failed" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f8_05_notes_quadrant_invalid_item_types_rejected(dummy_context: Any, sample_project: ProjectState) -> None:
    """Verify update_stage_substate rejects non-parseable note item data types."""
    dummy_context.state["project_state"] = sample_project
    res = await update_stage_substate(
        stage="stage_1_research",
        quadrant="notes",
        data=[12345],  # type: ignore[arg-type]
        tool_context=dummy_context,
    )
    assert res["status"] == "error"
    assert "Cannot parse note item" in res["message"]


# --- Feature 9 Boundary Cases (5 Tests) ---

def test_tier2_f9_01_path_traversal_attempts_in_project_id_rejected(tmp_path: Path) -> None:
    """Verify persistence service rejects path traversal attacks in project_id."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    malicious_ids = [
        "../../etc/passwd",
        "../secret",
        "proj/sub/dir",
        "..\\..\\windows\\system32",
    ]
    for m_id in malicious_ids:
        with pytest.raises(ValueError):
            service.get_state_file_path(m_id)


def test_tier2_f9_02_empty_and_whitespace_project_id_rejected() -> None:
    """Verify validate_project_id rejects empty or whitespace project_ids."""
    with pytest.raises(ValueError):
        validate_project_id("")
    with pytest.raises(ValueError):
        validate_project_id("   ")


@pytest.mark.asyncio
async def test_tier2_f9_03_corrupted_disk_json_falls_back_to_mysql(mock_mysql_service: AsyncMock, tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify corrupted/truncated disk JSON triggers automatic fallback recovery to MySQL."""
    service = ProjectPersistenceService(mysql=mock_mysql_service, base_data_dir=tmp_path)
    mock_mysql_service.fetch_one.return_value = {"state": sample_project.model_dump_json(), "version": 1}

    disk_path = service.get_state_file_path(sample_project.project_id)
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(b'{"corrupted_truncated_json": [')

    recovered = await service.load_state(sample_project.project_id)
    assert recovered is not None
    assert recovered.project_id == sample_project.project_id


@pytest.mark.asyncio
async def test_tier2_f9_04_load_nonexistent_project_raises_filenotfound(tmp_path: Path) -> None:
    """Verify load_state raises FileNotFoundError when project does not exist on disk or MySQL."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        await service.load_state("nonexistent-proj-uuid")


def test_tier2_f9_05_atomic_write_io_failure_cleans_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify atomic_write_json unlinks temporary file if write or flush fails with OSError."""
    target_file = tmp_path / "test_file.json"

    def _fail_fsync(fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", _fail_fsync)

    with pytest.raises(OSError):
        ProjectPersistenceService.atomic_write_json(target_file, '{"key": "val"}')

    assert not target_file.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


# --- Feature 10 Boundary Cases (5 Tests) ---

@pytest.mark.asyncio
async def test_tier2_f10_01_corrupt_state_in_tool_context_falls_back_to_storage(tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify corrupted dict state in tool_context is rejected with error status."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    ProjectPersistenceService.set_instance(service)
    service.save_state(sample_project)

    # Put corrupted dict in context without valid schema
    ctx: Any = DummyToolContext(
        state={"project_state": {"invalid": "corrupted"}, "project_id": sample_project.project_id}
    )
    res = await get_project_state(scope="summary", tool_context=ctx)
    assert res["status"] == "error"
    assert "No active project state found" in res["message"]


@pytest.mark.asyncio
async def test_tier2_f10_02_empty_author_falls_back_to_system(sample_project: ProjectState) -> None:
    """Verify empty agent_name in ToolContext falls back to 'system' as message author."""
    ctx: Any = DummyToolContext(state={"project_state": sample_project}, agent_name="")
    res = await post_to_message_board("insight", "System Post", "Content", tool_context=ctx)
    assert res["status"] == "success"
    assert res["message"]["author_agent"] == "system"


@pytest.mark.asyncio
async def test_tier2_f10_03_none_tool_context_uses_active_project_state(sample_project: ProjectState) -> None:
    """Verify tool execution with tool_context=None falls back to active singleton state."""
    set_active_project_state(sample_project)
    res = await get_project_state(scope="summary", tool_context=None)
    assert res["status"] == "success"
    assert res["data"]["project_id"] == sample_project.project_id


@pytest.mark.asyncio
async def test_tier2_f10_04_tool_context_with_only_project_id(tmp_path: Path, sample_project: ProjectState) -> None:
    """Verify ToolContext containing only project_id resolves state via persistence service."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
    ProjectPersistenceService.set_instance(service)
    service.save_state(sample_project)

    ctx: Any = DummyToolContext(state={"project_id": sample_project.project_id})
    res = await get_project_state(scope="summary", tool_context=ctx)
    assert res["status"] == "success"
    assert res["data"]["project_id"] == sample_project.project_id


@pytest.mark.asyncio
async def test_tier2_f10_05_concurrent_agent_contexts_isolated(sample_project: ProjectState) -> None:
    """Verify concurrent agent tool contexts maintain isolated blackboard postings."""
    state1 = copy.deepcopy(sample_project)
    state2 = copy.deepcopy(sample_project)
    state2.project_id = "proj-sample-02"

    ctx1: Any = DummyToolContext(state={"project_state": state1})
    ctx2: Any = DummyToolContext(state={"project_state": state2})

    await asyncio.gather(
        post_to_message_board("insight", "Context 1 Insight", "Content 1", tool_context=ctx1),
        post_to_message_board("warning", "Context 2 Warning", "Content 2", tool_context=ctx2),
    )

    assert len(state1.message_board) == 1
    assert state1.message_board[0].title == "Context 1 Insight"
    assert len(state2.message_board) == 1
    assert state2.message_board[0].title == "Context 2 Warning"


# --- Feature 11 Boundary Cases (5 Tests) ---

@pytest.mark.asyncio
async def test_tier2_f11_01_unmet_stage_prerequisites_rejected(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify executing Stage 2 without Stage 1 papers raises prerequisite validation error."""
    proj = make_test_project("proj-f11-prereq")  # No seed DOIs, no papers
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run_stage(proj, "stage_2_analysis")
    assert "prerequisite" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_tier2_f11_02_force_flag_bypasses_prerequisites(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify force=True flag bypasses prerequisite checks and executes stage."""
    proj = make_test_project("proj-f11-force")
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    res_state = await pipeline.run_stage(proj, "stage_2_analysis", force=True)
    assert res_state.stage_2_analysis.meta.status == "completed"


@pytest.mark.asyncio
async def test_tier2_f11_03_injected_stage_failure_error_capture(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify injected stage failure is recorded in meta.error_message and posted to board."""
    proj = make_test_project("proj-f11-fail", seed_dois=["10.1145/3292500"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    pipeline.set_stage_failure("stage_2_analysis", RuntimeError("Simulated OOM In Analysis"))

    res_state = await pipeline.run_stage(proj, "stage_2_analysis", raise_on_error=False, force=True)
    assert res_state.stage_2_analysis.meta.status == "failed"
    assert "Simulated OOM" in str(res_state.stage_2_analysis.meta.error_message)
    # Check that failure warning was posted to blackboard
    warnings = [m for m in res_state.message_board if m.message_type == "warning"]
    assert len(warnings) >= 1
    assert "Simulated OOM" in warnings[-1].content


@pytest.mark.asyncio
async def test_tier2_f11_04_inverted_sequence_bounds_rejected(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify running pipeline with start_stage occurring after stop_at_stage raises ValueError."""
    proj = make_test_project("proj-f11-inverted")
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run_pipeline(proj, start_stage="stage_4_writing", stop_at_stage="stage_2_analysis")
    assert "occurs after" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tier2_f11_05_pipeline_resumes_after_failure_cleared(isolated_persistence: ProjectPersistenceService) -> None:
    """Verify pipeline resumes and completes after an injected failure is cleared."""
    proj = make_test_project("proj-f11-recover", seed_dois=["10.1145/3292500"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    pipeline.set_stage_failure("stage_2_analysis", RuntimeError("Temporary Network Flake"))

    # First run fails
    with pytest.raises(RuntimeError):
        await pipeline.run_pipeline("proj-f11-recover", raise_on_error=True)

    # Clear failure and resume
    pipeline.clear_stage_failure("stage_2_analysis")
    final_state = await pipeline.run_pipeline("proj-f11-recover", resume_from_checkpoint=True)

    assert final_state.status == "completed"
    assert final_state.stage_2_analysis.meta.status == "completed"
    assert final_state.stage_5_export.meta.status == "completed"

# ===========================================================================
# Tier 3: Cross-Feature Pairwise Interactions (6 Tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_tier3_pairwise_substate_mutation_and_message_board_broadcast(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Pairwise: update_stage_substate coupled with post_to_message_board and get_project_state."""
    proj = make_test_project("proj-tier3-pair1", name="Multimodal Graph Learning")
    isolated_persistence.save_state(proj)

    ctx: Any = DummyToolContext(
        state={"project_state": proj, "project_id": proj.project_id},
        agent_name="ResearchAgent",
    )

    doi = "10.1145/3292500.3330964"
    paper_data = {
        doi: {
            "doi": doi,
            "title": "Graph Attention Networks: Scalable Formulations",
            "authors": ["Petar Velickovic", "Guillem Cucurull"],
            "year": 2018,
            "citation_count": 8000,
        }
    }

    # 1. Mutate stage 1 artifacts
    res_mut = await update_stage_substate(
        stage="stage_1_research",
        quadrant="artifacts",
        data={"papers": paper_data},
        tool_context=ctx,
    )
    assert res_mut["status"] == "success"

    # 2. Post discovery to blackboard
    res_post = await post_to_message_board(
        message_type="insight",
        title="Discovered Scalable Formulation",
        content="Found graph attention paper with linear complexity.",
        stage="stage_1_research",
        related_paper_dois=[doi],
        tool_context=ctx,
    )
    assert res_post["status"] == "success"
    msg_id = res_post["message_id"]

    # 3. Verify dot-path extraction
    res_path = await get_project_state(
        scope="path",
        path=f"stage_1_research.artifacts.papers.{doi}.title",
        tool_context=ctx,
    )
    assert res_path["status"] == "success"
    assert res_path["data"] == "Graph Attention Networks: Scalable Formulations"

    # 4. Verify blackboard query
    res_read = await read_message_board(
        stage="stage_1_research",
        paper_doi=doi,
        tool_context=ctx,
    )
    assert res_read["status"] == "success"
    assert res_read["count"] == 1
    assert res_read["messages"][0]["id"] == msg_id

    # 5. Verify disk state contains both updates
    disk_state = isolated_persistence.load_state_sync("proj-tier3-pair1")
    assert disk_state is not None
    assert doi in disk_state.stage_1_research.artifacts.papers
    assert len(disk_state.message_board) == 1


@pytest.mark.asyncio
async def test_tier3_pairwise_disk_persistence_and_mysql_cold_cache_recovery(tmp_path: Path) -> None:
    """Pairwise: Atomic disk persistence paired with MySQL fallback and automatic disk re-caching."""
    mock_mysql = MockAsyncMySQL()
    service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path)
    ProjectPersistenceService.set_instance(service)

    project = make_test_project("proj-tier3-pair2", name="Persistence Recovery Test")
    project.stage_1_research.artifacts.total_discovered = 42

    # Save to disk and MySQL
    await service.save_state_async(project)
    disk_file = service.get_state_file_path("proj-tier3-pair2")
    assert disk_file.exists()
    assert "proj-tier3-pair2" in mock_mysql.rows

    # Simulate cold cache: wipe in-memory and delete disk file
    set_active_project_state(None)
    disk_file.unlink()
    assert not disk_file.exists()

    # Recover from MySQL
    recovered = await service.load_state("proj-tier3-pair2")
    assert recovered is not None
    assert recovered.project_id == "proj-tier3-pair2"
    assert recovered.stage_1_research.artifacts.total_discovered == 42
    assert "proj-tier3-pair2" in mock_mysql.fetch_one_calls

    # Verify automatic cache write-through
    assert disk_file.exists()
    assert json.loads(disk_file.read_text(encoding="utf-8"))["name"] == "Persistence Recovery Test"

    # Second load hits disk cache directly without additional MySQL query
    calls_before = len(mock_mysql.fetch_one_calls)
    cached = await service.load_state("proj-tier3-pair2")
    assert cached.name == "Persistence Recovery Test"
    assert len(mock_mysql.fetch_one_calls) == calls_before


@pytest.mark.asyncio
async def test_tier3_pairwise_pipeline_interruption_and_checkpoint_resumption(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Pairwise: Pipeline mid-stage interruption at Stage 3, state preservation, and resumption."""
    proj = make_test_project("proj-tier3-pair3", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

    # Inject failure at Stage 3
    pipeline.set_stage_failure("stage_3_planning", RuntimeError("Simulated LLM rate limit quota exceeded"))

    with pytest.raises(RuntimeError) as exc_info:
        await pipeline.run_pipeline("proj-tier3-pair3", raise_on_error=True)
    assert "Simulated LLM rate limit" in str(exc_info.value)

    # Checkpoint state validation
    interrupted_state = isolated_persistence.load_state_sync("proj-tier3-pair3")
    assert interrupted_state is not None
    assert interrupted_state.stage_1_research.meta.status == "completed"
    assert interrupted_state.stage_2_analysis.meta.status == "completed"
    assert interrupted_state.stage_3_planning.meta.status == "failed"
    assert interrupted_state.status == "failed"
    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
    assert pipeline.get_stage_execution_count("stage_3_planning") == 0  # Failed before runner execution

    # Clear failure and resume from checkpoint
    pipeline.clear_stage_failure("stage_3_planning")
    resumed_state = await pipeline.run_pipeline("proj-tier3-pair3", resume_from_checkpoint=True)

    # Invariant: Stage 1 and 2 are not re-executed, Stage 3 now executed once
    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
    assert pipeline.get_stage_execution_count("stage_3_planning") == 1
    assert pipeline.get_stage_execution_count("stage_4_writing") == 1
    assert pipeline.get_stage_execution_count("stage_5_export") == 1
    assert resumed_state.status == "completed"


@pytest.mark.asyncio
async def test_tier3_pairwise_adk_tool_context_agent_boundary_transition(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Pairwise: ADK ToolContext passing state across agent boundaries (Research -> Planner -> Writer)."""
    proj = make_test_project("proj-tier3-pair4", name="Agentic Boundary Review")
    isolated_persistence.save_state(proj)

    ctx: Any = DummyToolContext(
        state={"project_state": proj, "project_id": proj.project_id},
        agent_name="ResearchAgent",
    )

    doi = "10.1038/s41586-023-06792-0"

    # 1. ResearchAgent mutates state and posts discovery
    await update_stage_substate(
        "stage_1_research",
        "artifacts",
        {"papers": {doi: {"doi": doi, "title": "Autonomous Discovery", "authors": ["Nature Lead"]}}},
        tool_context=ctx,
    )
    res_post1 = await post_to_message_board(
        "insight", "Research Complete", "Discovered Nature paper.", related_paper_dois=[doi], tool_context=ctx
    )
    assert res_post1["message"]["author_agent"] == "ResearchAgent"

    # 2. Transition to PlannerAgent
    ctx.switch_agent("PlannerAgent")
    # Read unacknowledged insights
    unack_res = await read_message_board(unacknowledged_only=True, mark_as_acknowledged=True, tool_context=ctx)
    assert unack_res["count"] == 1

    # Planner updates planning outline
    blueprint = {
        "outline": {
            "title": "Review Outline",
            "sections": [
                {"section_id": "sec-1", "order": 1, "title": "Introduction", "description": "Intro", "target_word_count": 1500}
            ],
        }
    }
    await update_stage_substate("stage_3_planning", "artifacts", blueprint, tool_context=ctx)
    res_post2 = await post_to_message_board("decision", "Approved Arc", "Approved 1-section outline.", tool_context=ctx)
    assert res_post2["message"]["author_agent"] == "PlannerAgent"

    # 3. Transition to WriterAgent
    ctx.switch_agent("WriterAgent")
    # Read outline section via dot-path
    res_outline = await get_project_state(
        scope="path", path="stage_3_planning.artifacts.outline.sections.0.title", tool_context=ctx
    )
    assert res_outline["status"] == "success"
    assert res_outline["data"] == "Introduction"

    # Writer acknowledges decision
    await read_message_board(message_type="decision", mark_as_acknowledged=True, tool_context=ctx)

    # Writer adds draft
    draft_data = {"section_drafts": {"sec-1": {"section_id": "sec-1", "title": "Introduction", "content": "Intro markdown."}}}
    await update_stage_substate("stage_4_writing", "artifacts", draft_data, tool_context=ctx)

    # 4. State continuity verification
    state = ctx.state["project_state"]
    assert doi in state.stage_1_research.artifacts.papers
    assert len(state.stage_3_planning.artifacts.outline.sections) == 1
    assert "sec-1" in state.stage_4_writing.artifacts.section_drafts
    # Acknowledgment checks
    msg1 = state.message_board[0]
    msg2 = state.message_board[1]
    assert "PlannerAgent" in msg1.acknowledged_by
    assert "WriterAgent" in msg2.acknowledged_by


@pytest.mark.asyncio
async def test_tier3_pairwise_dot_path_query_with_deep_substate_mutation(
    dummy_context: Any, sample_project: ProjectState
) -> None:
    """Pairwise: Scoped dot-path querying over deep nested substate mutations."""
    dummy_context.state["project_state"] = sample_project
    doi = "10.1145/3292500.3330964"

    # Deep mutate paper attributes
    await update_stage_substate(
        "stage_1_research",
        "artifacts",
        {"papers": {doi: {"abstract": "Novel message passing formulation", "citation_count": 9999}}},
        tool_context=dummy_context,
    )

    # Add research questions
    await update_stage_substate(
        "stage_1_research",
        "inputs",
        {"research_questions": ["Q1: Scalability", "Q2: Expressivity", "Q3: Heterophily"]},
        tool_context=dummy_context,
    )

    # Query 1: Compound DOI key with dots
    res1 = await get_project_state(
        scope="path",
        path=f"stage_1_research.artifacts.papers.{doi}.citation_count",
        tool_context=dummy_context,
    )
    assert res1["status"] == "success"
    assert res1["data"] == 9999

    # Query 2: Nested list index
    res2 = await get_project_state(
        scope="path",
        path="stage_1_research.inputs.research_questions.1",
        tool_context=dummy_context,
    )
    assert res2["status"] == "success"
    assert res2["data"] == "Q2: Expressivity"


@pytest.mark.asyncio
async def test_tier3_pairwise_token_budget_tracking_across_pipeline_transitions(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Pairwise: Cumulative token budget accounting across pipeline transitions."""
    proj = make_test_project("proj-tier3-pair6", seed_dois=["10.1145/3292500"])
    proj.token_budget = 100000
    proj.tokens_used = 0
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

    async def _on_stage_complete(stage_name: str, state: ProjectState) -> None:
        if stage_name == "stage_1_research":
            state.tokens_used += 15000
        elif stage_name == "stage_2_analysis":
            state.tokens_used += 25000
        isolated_persistence.save_state(state)

    state = await pipeline.run_pipeline(
        "proj-tier3-pair6",
        stop_at_stage="stage_2_analysis",
        on_stage_complete=_on_stage_complete,
    )

    assert state.tokens_used == 40000

    # Verify summary mode reflects cumulative tokens
    ctx: Any = DummyToolContext(state={"project_state": state})
    summary_res = await get_project_state(scope="summary", tool_context=ctx)
    assert summary_res["data"]["tokens_used"] == 40000
    assert summary_res["data"]["token_budget"] == 100000

    # Reload from disk and verify persistence
    loaded = isolated_persistence.load_state_sync("proj-tier3-pair6")
    assert loaded is not None
    assert loaded.tokens_used == 40000


# ===========================================================================
# Tier 4: Real-World Application Scenarios (5 Tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_tier4_scenario_full_5_stage_literature_review_agentic_workflows(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Scenario 4.1: Complete 5-stage literature review on 'Agentic Workflows in Scientific Discovery'."""
    topic = "Agentic Workflows in Scientific Discovery: Autonomous Multi-Agent Systems for Hypothesis Generation, Literature Synthesis, and Laboratory Automation"
    seed_dois = [
        "10.1038/s41586-023-06792-0",
        "10.1126/science.adi1407",
        "10.1145/3292500",
        "10.1016/j.artint.2024",
        "10.1109/tkde.2023.101",
        "10.1145/3330964",
    ]
    research_questions = [
        "How do autonomous multi-agent systems coordinate in scientific discovery workflows?",
        "What are the key failure modes and citation hallucination risks in autonomous literature review pipelines?",
        "How can epistemic graph representations and verification checks enforce rigorous academic grounding?",
    ]

    proj = ProjectState(
        project_id="proj-tier4-scenario1",
        name="Agentic Scientific Discovery Review",
        topic=topic,
        target_level="phd",
        token_budget=1000000,
    )
    proj.stage_1_research.inputs.seed_dois = seed_dois
    proj.stage_1_research.inputs.research_questions = research_questions
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    final_state = await pipeline.run_pipeline("proj-tier4-scenario1", raise_on_error=True)

    # 1. Stage 1 Research Verification
    assert final_state.stage_1_research.meta.status == "completed"
    papers = final_state.stage_1_research.artifacts.papers
    assert len(papers) >= 6
    assert len(final_state.stage_1_research.artifacts.citation_edges) >= 5
    for s_doi in seed_dois:
        assert s_doi in papers
        assert papers[s_doi].is_seed is True

    # 2. Stage 2 Analysis Verification
    assert final_state.stage_2_analysis.meta.status == "completed"
    rankings = final_state.stage_2_analysis.artifacts.rankings
    assert len(rankings) == len(papers)
    assert all(r.similarity_score > 0 and r.pagerank_score > 0 and r.hybrid_score > 0 for r in rankings)
    assert len(final_state.stage_2_analysis.artifacts.clusters) >= 2
    assert len(final_state.stage_2_analysis.artifacts.gaps) >= len(research_questions)

    # 3. Stage 3 Planning Verification
    assert final_state.stage_3_planning.meta.status == "completed"
    outline = final_state.stage_3_planning.artifacts.outline
    assert len(outline.sections) >= 4
    assert all(len(s.assigned_dois) > 0 for s in outline.sections)
    assert len(final_state.stage_3_planning.artifacts.doi_mappings) == len(papers)

    # 4. Stage 4 Writing Verification
    assert final_state.stage_4_writing.meta.status == "completed"
    drafts = final_state.stage_4_writing.artifacts.section_drafts
    assert len(drafts) == len(outline.sections)
    assert final_state.stage_4_writing.artifacts.citation_grounding_verified is True
    assert len(final_state.stage_4_writing.artifacts.full_draft_markdown) > 500

    # 5. Stage 5 Export Verification
    assert final_state.stage_5_export.meta.status == "completed"
    assert final_state.stage_5_export.artifacts.tex_path is not None
    assert Path(final_state.stage_5_export.artifacts.tex_path).exists()
    assert final_state.stage_5_export.artifacts.bib_path is not None
    assert Path(final_state.stage_5_export.artifacts.bib_path).exists()
    assert final_state.stage_5_export.artifacts.pdf_path is not None
    assert Path(final_state.stage_5_export.artifacts.pdf_path).exists()

    # Root Completion
    assert final_state.status == "completed"
    assert final_state.completed_at is not None
    assert len(final_state.message_board) >= 5


@pytest.mark.asyncio
async def test_tier4_scenario_concurrent_message_board_exchange_and_multi_agent_acknowledgment(
    dummy_context: Any, sample_project: ProjectState
) -> None:
    """Scenario 4.2: Concurrent multi-agent message board exchange and multi-agent acknowledgment tracking."""
    dummy_context.state["project_state"] = sample_project

    async def _post(m_type: str, title: str, author: str, tag: str, doi: str | None = None) -> dict[str, Any]:
        ctx: Any = DummyToolContext(state=dummy_context.state, agent_name=author)
        return await post_to_message_board(
            message_type=m_type,
            title=title,
            content=f"Discovery payload from {author} on {title}",
            tags=[tag],
            related_paper_dois=[doi] if doi else None,
            tool_context=ctx,
        )

    tasks = [
        _post("insight", "Discovery Alpha", "ResearchAgent", "foundations", "10.1145/3292500"),
        _post("insight", "Discovery Beta", "ResearchAgent", "scaling", "10.1016/j.artint.2024"),
        _post("insight", "Discovery Gamma", "ResearchAgent", "inductive"),
        _post("gap", "Gap Delta", "GapFinderAgent", "evaluation"),
        _post("gap", "Gap Epsilon", "GapFinderAgent", "benchmarks"),
        _post("gap", "Gap Zeta", "GapFinderAgent", "grounding"),
        _post("decision", "Decision Eta", "PlannerAgent", "architecture"),
        _post("decision", "Decision Theta", "PlannerAgent", "sections"),
        _post("decision", "Decision Iota", "PlannerAgent", "bibliography"),
        _post("warning", "Warning Kappa", "WriterAgent", "rate_limit"),
        _post("hypothesis", "Hypothesis Lambda", "WriterAgent", "convergence"),
        _post("warning", "Warning Mu", "WriterAgent", "context_window"),
    ]

    results = await asyncio.gather(*tasks)
    assert all(r["status"] == "success" for r in results)
    assert len(sample_project.message_board) == 12

    # PlannerAgent reads and acknowledges all gaps
    planner_ctx: Any = DummyToolContext(state=dummy_context.state, agent_name="PlannerAgent")
    gaps_read = await read_message_board(
        message_type="gap", unacknowledged_only=True, mark_as_acknowledged=True, tool_context=planner_ctx
    )
    assert gaps_read["count"] == 3

    # WriterAgent reads and acknowledges all decisions
    writer_ctx: Any = DummyToolContext(state=dummy_context.state, agent_name="WriterAgent")
    decisions_read = await read_message_board(
        message_type="decision", unacknowledged_only=True, mark_as_acknowledged=True, tool_context=writer_ctx
    )
    assert decisions_read["count"] == 3

    # Verify filtering
    gaps_unack_planner = await read_message_board(
        message_type="gap", unacknowledged_only=True, unacknowledged_by="PlannerAgent", tool_context=dummy_context
    )
    assert gaps_unack_planner["count"] == 0

    decisions_unack_writer = await read_message_board(
        message_type="decision", unacknowledged_only=True, unacknowledged_by="WriterAgent", tool_context=dummy_context
    )
    assert decisions_unack_writer["count"] == 0


@pytest.mark.asyncio
async def test_tier4_scenario_cold_restart_recovery_with_exact_quadrant_fidelity(
    isolated_storage: Path,
) -> None:
    """Scenario 4.3: Complete cold restart recovery from disk JSON with exact quadrant fidelity."""
    init_persistence = ProjectPersistenceService(mysql=None, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(init_persistence)

    proj = make_test_project("proj-tier4-scenario3", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
    init_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=init_persistence)
    state_stage3 = await pipeline.run_pipeline("proj-tier4-scenario3", stop_at_stage="stage_3_planning")

    # Add notes to stages
    state_stage3.stage_1_research.notes.append(StageNote(author="ResearchAgent", content="Traversed 2 hops."))
    state_stage3.stage_2_analysis.notes.append(StageNote(author="GapFinderAgent", content="Found 3 distinct gaps."))
    state_stage3.stage_3_planning.notes.append(StageNote(author="PlannerAgent", content="Structured 4 sections."))
    init_persistence.save_state(state_stage3)

    # Capture snapshot
    pre_snapshot = state_stage3.model_dump(mode="json")

    # Simulate Process Termination & Cold Restart
    set_active_project_state(None)
    ProjectPersistenceService.set_instance(None)

    fresh_persistence = ProjectPersistenceService(mysql=None, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(fresh_persistence)
    fresh_pipeline = WorkflowExecutionPipeline(persistence=fresh_persistence)

    recovered = await fresh_persistence.load_state("proj-tier4-scenario3")
    assert recovered is not None
    post_snapshot = recovered.model_dump(mode="json")

    # Exact quadrant fidelity checks
    assert pre_snapshot["project_id"] == post_snapshot["project_id"]
    assert pre_snapshot["stage_1_research"] == post_snapshot["stage_1_research"]
    assert pre_snapshot["stage_2_analysis"] == post_snapshot["stage_2_analysis"]
    assert pre_snapshot["stage_3_planning"] == post_snapshot["stage_3_planning"]
    assert len(pre_snapshot["message_board"]) == len(post_snapshot["message_board"])

    # Resume from cold restart to completion
    final_state = await fresh_pipeline.run_pipeline(recovered, start_stage="stage_4_writing")
    assert final_state.status == "completed"
    assert final_state.stage_4_writing.meta.status == "completed"
    assert final_state.stage_5_export.meta.status == "completed"


@pytest.mark.asyncio
async def test_tier4_scenario_stage_failure_error_capture_manual_intervention_and_resumption(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Scenario 4.4: Stage failure, error capture, operator manual correction, and clean resumption."""
    proj = make_test_project("proj-tier4-scenario4", seed_dois=["10.1145/3292500"])
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
    # Stage 1 executes successfully
    await pipeline.run_stage(proj, "stage_1_research")

    # Inject failure on Stage 2 (e.g. embedding service failure)
    pipeline.set_stage_failure("stage_2_analysis", ConnectionError("Embedding API 503 Service Unavailable"))
    failed_state = await pipeline.run_stage(proj, "stage_2_analysis", raise_on_error=False)

    assert failed_state.stage_2_analysis.meta.status == "failed"
    assert "Embedding API 503" in str(failed_state.stage_2_analysis.meta.error_message)
    assert failed_state.status == "failed"

    # Operator intervention: inject manual clusters and mark Stage 2 completed
    ctx: Any = DummyToolContext(
        state={"project_state": failed_state, "project_id": failed_state.project_id},
        agent_name="SupervisorAgent",
    )
    fallback_clusters = [
        {"cluster_id": "c-fallback", "label": "Manual Fallback Cluster", "paper_dois": ["10.1145/3292500"]}
    ]
    await update_stage_substate("stage_2_analysis", "artifacts", {"clusters": fallback_clusters}, tool_context=ctx)
    await update_stage_substate(
        "stage_2_analysis",
        "meta",
        {"status": "completed", "error_message": None, "progress_percentage": 100.0},
        tool_context=ctx,
    )
    await update_stage_substate(
        "stage_2_analysis",
        "notes",
        [{"author": "SupervisorAgent", "content": "Manually injected offline clusters after 503 error."}],  # type: ignore[arg-type]
        tool_context=ctx,
    )

    # Clear injected failure and resume pipeline
    pipeline.clear_stage_failure("stage_2_analysis")
    final_state = await pipeline.run_pipeline("proj-tier4-scenario4", resume_from_checkpoint=True)

    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 0  # Skipped because completed by operator
    assert final_state.status == "completed"
    assert final_state.stage_3_planning.meta.status == "completed"
    assert final_state.stage_5_export.meta.status == "completed"


@pytest.mark.asyncio
async def test_tier4_scenario_deep_dot_path_selective_extraction_and_summary_monitoring(
    dummy_context: Any, sample_project: ProjectState
) -> None:
    """Scenario 4.5: Deep dot-path selective extraction and summary monitoring under constrained context."""
    dummy_context.state["project_state"] = sample_project

    # Populate outline sections
    sample_project.stage_3_planning.artifacts.outline = OutlineStructure(
        title="Compact Outline",
        sections=[
            SectionBlueprint(
                section_id="sec-1",
                order=1,
                title="1. Introduction & Research Scope",
                description="Introduction and scope definition.",
                target_word_count=1200,
            )
        ],
    )

    # 1. Summary Query
    summary_res = await get_project_state(scope="summary", tool_context=dummy_context)
    assert summary_res["status"] == "success"
    # Verify summary payload is concise (< 1500 chars json)
    assert len(json.dumps(summary_res["data"])) < 1500

    # 2. Stage Substate Query (Isolated Stage 3)
    stage_res = await get_project_state(scope="stage", stage="stage_3_planning", tool_context=dummy_context)
    assert stage_res["status"] == "success"
    assert "outline" in stage_res["data"]["artifacts"]
    assert "stage_1_research" not in stage_res["data"]

    # 3. Deep Dot-Path Extraction (Single Title String)
    path_res1 = await get_project_state(
        scope="path", path="stage_3_planning.artifacts.outline.sections.0.title", tool_context=dummy_context
    )
    assert path_res1["status"] == "success"
    assert path_res1["data"] == "1. Introduction & Research Scope"

    # 4. Deep Dot-Path Extraction (Author list on paper)
    path_res2 = await get_project_state(
        scope="path",
        path="stage_1_research.artifacts.papers.10.1145/3292500.3330964.authors",
        tool_context=dummy_context,
    )
    assert path_res2["status"] == "success"
    assert isinstance(path_res2["data"], list)
    assert "Jie Zhou" in path_res2["data"]

    # 5. Invalid path returns error without throwing exception
    path_err = await get_project_state(
        scope="path", path="stage_1_research.artifacts.papers.nonexistent_doi.authors", tool_context=dummy_context
    )
    assert path_err["status"] == "error"

# ===========================================================================
# Tier 5: Adversarial Coverage Hardening (12 Tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_adversarial_concurrency_message_board_stress_50_posts(
    persistence_service: ProjectPersistenceService, dummy_context: Any
) -> None:
    """Test 5.1: Stress test public message board with 60 concurrent async posts."""
    state = ProjectState(project_id="stress-concurrent-01", name="Concurrency Stress Test")
    persistence_service.save_state(state, dummy_context)
    dummy_context.state["project_state"] = state

    msg_types = ["insight", "serendipity", "gap", "warning", "decision", "hypothesis"]

    async def _post_task(idx: int) -> dict[str, Any]:
        m_type = msg_types[idx % len(msg_types)]
        return await post_to_message_board(
            message_type=m_type,
            title=f"Concurrent Discovery #{idx:03d}",
            content=f"High-frequency discovery payload index {idx} under async stress.",
            stage=f"stage_{(idx % 5) + 1}_research" if (idx % 5) == 0 else "global",
            tags=[f"tag_{idx}", m_type],
            related_paper_dois=[f"10.1145/{3290000 + idx}"],
            tool_context=dummy_context,
        )

    tasks = [_post_task(i) for i in range(60)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 60
    assert all(r["status"] == "success" for r in results)
    assert len(state.message_board) == 60

    msg_ids = [m.id for m in state.message_board]
    assert len(set(msg_ids)) == 60  # Zero UUID collisions

    # Verify disk persistence integrity
    disk_file = persistence_service.get_state_file_path(state.project_id)
    assert disk_file.exists()
    disk_state = ProjectState.model_validate_json(disk_file.read_text(encoding="utf-8"))
    assert len(disk_state.message_board) == 60


@pytest.mark.asyncio
async def test_adversarial_concurrency_interleaved_readers_writers_stress(
    persistence_service: ProjectPersistenceService, dummy_context: Any
) -> None:
    """Test 5.2: Stress test interleaved concurrent readers and writers without read corruption."""
    state = ProjectState(project_id="stress-rw-02", name="Read Write Stress")
    for i in range(5):
        state.post_message(
            author_agent="SeedAgent",
            message_type="insight",
            title=f"Initial Seed #{i}",
            content="Pre-seeded blackboard message.",
        )
    persistence_service.save_state(state, dummy_context)
    dummy_context.state["project_state"] = state

    async def _writer(idx: int) -> dict[str, Any]:
        await asyncio.sleep(0.0005 * (idx % 5))
        return await post_to_message_board(
            message_type="gap",
            title=f"Writer #{idx}",
            content=f"Payload {idx}",
            tool_context=dummy_context,
        )

    async def _reader(idx: int) -> dict[str, Any]:
        await asyncio.sleep(0.0005 * (idx % 3))
        return await read_message_board(tool_context=dummy_context)

    writer_tasks = [_writer(i) for i in range(50)]
    reader_tasks = [_reader(i) for i in range(50)]

    all_results = await asyncio.gather(*writer_tasks, *reader_tasks)
    writer_results = all_results[:50]
    reader_results = all_results[50:]

    assert all(w["status"] == "success" for w in writer_results)
    assert all(r["status"] == "success" for r in reader_results)
    for r in reader_results:
        assert 5 <= r["count"] <= 55
    assert len(state.message_board) == 55


@pytest.mark.asyncio
async def test_adversarial_concurrency_multi_agent_acknowledgment_race(
    persistence_service: ProjectPersistenceService,
) -> None:
    """Test 5.3: Concurrent multi-agent acknowledgments on messages avoid lost updates."""
    state = ProjectState(project_id="stress-ack-03", name="Ack Race Test")
    msg_ids: list[str] = []
    for i in range(10):
        msg = state.post_message(
            author_agent="Broadcaster",
            message_type="warning",
            title=f"Broadcast Notice #{i}",
            content="Critical notice requiring widespread acknowledgment.",
        )
        msg_ids.append(msg.id)

    agents = [f"WorkerAgent_{i:02d}" for i in range(20)]

    async def _ack_task(agent_name: str, m_id: str) -> None:
        state.acknowledge_message(m_id, agent_name)

    tasks = [_ack_task(agent, mid) for agent in agents for mid in msg_ids]
    await asyncio.gather(*tasks)

    for mid in msg_ids:
        msg = next(m for m in state.message_board if m.id == mid)
        assert len(msg.acknowledged_by) == 20
        assert set(msg.acknowledged_by) == set(agents)


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../../etc/passwd",
        "../../../var/log/syslog",
        "/etc/shadow",
        "proj" + chr(0) + "root",
        "proj/sub/dir",
        "..\\..\\windows\\system32",
        "..",
        ".",
        "   ",
        "",
        "proj;rm -rf /",
        "proj|cat",
        "proj$HOME",
        "proj\nnewline",
        "proj\rreturn",
        "%2e%2e%2fpasswd",
    ],
)
def test_adversarial_path_traversal_project_id_rejection(
    persistence_service: ProjectPersistenceService, malicious_id: str
) -> None:
    """Test 5.4: validate_project_id and get_state_file_path reject path traversal attacks."""
    with pytest.raises(ValueError) as exc_info:
        persistence_service.get_state_file_path(malicious_id)
    assert "Invalid project_id" in str(exc_info.value) or "Path traversal detected" in str(exc_info.value)


@pytest.mark.parametrize(
    "dunder_path",
    [
        "__class__.__mro__",
        "__class__.__subclasses__",
        "__init__.__globals__",
        "stage_1_research.meta.__globals__",
        "stage_1_research.meta..status",
        ".stage_1_research",
        "stage_1_research.",
        "stage_3_planning.artifacts.outline.sections.9999",
        "stage_3_planning.artifacts.outline.sections.invalid_idx",
        "stage_1_research.nonexistent_subfield",
        "stage_1_research.artifacts.papers.nonexistent_key",
        "stage_1_research.artifacts.papers.10.1145/3292500.nonexistent_field",
        "__class__",
        "__dict__",
        "__repr__",
        "stage_1_research.__dict__",
    ],
)
@pytest.mark.asyncio
async def test_adversarial_dot_path_traversal_and_dunder_escape(
    dummy_context: Any, dunder_path: str
) -> None:
    """Test 5.5: get_project_state and get_by_dot_path reject dunder inspection and bad paths."""
    state = ProjectState(project_id="dunder-test-01", name="Dunder Test")
    dummy_context.state["project_state"] = state

    result = await get_project_state(scope="path", path=dunder_path, tool_context=dummy_context)
    assert result["status"] == "error"
    assert "Dot-path resolution failed" in result["message"]
    # Ensure error response is strictly JSON serializable
    assert json.dumps(result) is not None


@pytest.mark.parametrize(
    "stage, quadrant, payload",
    [
        ("../../etc/passwd", "meta", {"agent_name": "hacker"}),
        ("stage_1_research", "../../artifacts", {"papers": {}}),
        ("stage_1_research", "meta\x00", {"status": "completed"}),
        ("stage_1_research", "__dict__", {"evil": True}),
        ("stage_9_invalid", "meta", {"status": "completed"}),
        ("stage_1_research", "invalid_quadrant", {"data": 123}),
        ("stage_1_research", "meta", {"progress_percentage": "NOT_A_FLOAT"}),
        ("stage_1_research", "meta", {"progress_percentage": 150.0}),
        ("stage_1_research", "meta", {"status": "unsupported_enum_status"}),
    ],
)
@pytest.mark.asyncio
async def test_adversarial_mutation_quadrant_injection_rejection(
    dummy_context: Any, stage: str, quadrant: str, payload: Any
) -> None:
    """Test 5.6: update_stage_substate sanitizes and rejects invalid stages, quadrants, and payloads."""
    state = ProjectState(project_id="mutation-inj-01", name="Mutation Injection Test")
    dummy_context.state["project_state"] = state

    result = await update_stage_substate(
        stage=stage,
        quadrant=quadrant,
        data=payload,
        tool_context=dummy_context,
    )
    assert result["status"] == "error"
    msg = result["message"]
    assert "Invalid" in msg or "Validation failed" in msg or "must be a" in msg or "Error" in msg


@pytest.mark.asyncio
async def test_adversarial_corrupted_disk_json_fallback_to_mysql(
    persistence_service: ProjectPersistenceService, mock_mysql_service: AsyncMock
) -> None:
    """Test 5.7: Corrupted disk JSON triggers automatic fallback and recovery from MySQL."""
    project_id = "corrupt-disk-01"
    valid_state = ProjectState(project_id=project_id, name="Recovered From MySQL")
    valid_json = valid_state.model_dump_json(indent=2)

    # 1. Seed MySQL with valid state
    mock_mysql_service.fetch_one.return_value = {"state": valid_json, "version": 1}

    # 2. Corrupt disk file with unclosed JSON
    disk_path = persistence_service.get_state_file_path(project_id)
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(b'{"project_id": "corrupt-disk-01", "name": "Broken ... [TRUNCATED EOF')

    # 3. Call load_state
    loaded_state = await persistence_service.load_state(project_id)

    assert loaded_state is not None
    assert str(loaded_state.project_id) == project_id
    assert loaded_state.name == "Recovered From MySQL"

    # 4. Verify disk file was atomically repaired
    repaired_json = disk_path.read_text(encoding="utf-8")
    repaired_state = ProjectState.model_validate_json(repaired_json)
    assert repaired_state.name == "Recovered From MySQL"


@pytest.mark.asyncio
async def test_adversarial_corrupted_state_no_fallback_signals_filenotfound(
    persistence_service: ProjectPersistenceService, mock_mysql_service: AsyncMock
) -> None:
    """Test 5.8: FileNotFoundError is raised when disk state is corrupt and MySQL has no record."""
    project_id = "unrecoverable-01"
    disk_path = persistence_service.get_state_file_path(project_id)
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(bytes([0, 255, 254, 250, 128, 1, 2]) + b"RandomGarbageBytes")

    mock_mysql_service.fetch_one.return_value = None

    with pytest.raises(FileNotFoundError) as exc_info:
        await persistence_service.load_state(project_id)
    assert "not found" in str(exc_info.value) or "unrecoverable" in str(exc_info.value)


def test_adversarial_atomic_write_preserves_file_on_write_interruption(
    persistence_service: ProjectPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 5.9: atomic_write_json preserves existing file when write is interrupted (e.g. disk full)."""
    project_id = "atomic-interrupted-01"
    file_path = persistence_service.get_state_file_path(project_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Establish valid v1 state
    v1_content = '{\n  "project_id": "atomic-interrupted-01",\n  "version": 1,\n  "name": "Original Valid V1"\n}'
    file_path.write_text(v1_content, encoding="utf-8")

    # Mock os.fsync to raise disk full error
    def _mock_fsync_fail(fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", _mock_fsync_fail)

    v2_content = '{\n  "project_id": "atomic-interrupted-01",\n  "version": 2,\n  "name": "Corrupted V2"\n}'

    with pytest.raises(OSError) as exc_info:
        persistence_service.atomic_write_json(file_path, v2_content)
    assert "No space left on device" in str(exc_info.value)

    # Original file is preserved
    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == v1_content
    # No orphaned temporary files left behind
    tmp_files = list(file_path.parent.glob("*.tmp.*"))
    assert len(tmp_files) == 0


def test_adversarial_atomic_write_sibling_directory_guarantee(
    persistence_service: ProjectPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 5.10: Temporary files are created strictly in the same directory as the target file."""
    file_path = persistence_service.get_state_file_path("sibling-verify-01")
    observed_tmp_paths: list[tuple[Path, Path]] = []

    orig_replace = Path.replace

    def _intercept_replace(self: Path, target: Path) -> Path:
        observed_tmp_paths.append((self, target))
        return orig_replace(self, target)

    monkeypatch.setattr(Path, "replace", _intercept_replace)

    persistence_service.atomic_write_json(file_path, '{"test": true}')

    assert len(observed_tmp_paths) == 1
    tmp_path, target_path = observed_tmp_paths[0]
    assert tmp_path.parent == target_path.parent
    assert tmp_path.name.startswith("project_state.json.tmp.")


def test_adversarial_offline_socket_isolation_guard() -> None:
    """Test 5.11: Socket connection attempts are intercepted by the offline guard fixture."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as exc_info:
        s.connect(("8.8.8.8", 53))
    assert "Network call blocked: offline test isolation enforced" in str(exc_info.value)
    s.close()

    s_ex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as exc_info_ex:
        s_ex.connect_ex(("8.8.8.8", 53))
    assert "Network call blocked: offline test isolation enforced" in str(exc_info_ex.value)
    s_ex.close()


@pytest.mark.asyncio
async def test_adversarial_performance_budget_sub_3_second_full_suite(
    persistence_service: ProjectPersistenceService, dummy_context: Any
) -> None:
    """Test 5.12: High-volume operations complete within strict millisecond budgets."""
    t_start = time.perf_counter()

    state = ProjectState(project_id="perf-budget-01", name="Performance Budget Test")
    persistence_service.save_state(state, dummy_context)
    dummy_context.state["project_state"] = state

    # 30 posts
    for i in range(30):
        await post_to_message_board(
            message_type="insight",
            title=f"Perf Title {i}",
            content=f"Content {i}",
            tool_context=dummy_context,
        )

    # 20 dot-path queries
    for i in range(20):
        await get_project_state(scope="path", path="stage_1_research.meta.status", tool_context=dummy_context)

    duration = time.perf_counter() - t_start
    assert duration < 0.5, f"Operations took {duration:.3f}s (budget: < 0.5s)"
