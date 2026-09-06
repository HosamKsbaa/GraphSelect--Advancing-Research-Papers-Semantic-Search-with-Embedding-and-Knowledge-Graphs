"""Comprehensive test suite for the ALRS v2 Workflow Execution Pipeline.

Tests Requirement R6:
1. Full end-to-end multi-stage pipeline run (Stages 1 through 5).
2. Step-by-step single stage execution and stage alias/numeric resolution.
3. Inter-stage quadrant hydration (Artifacts_N -> Inputs_{N+1}).
4. Public Message Board cross-stage posting, querying, and acknowledgment isolation.
5. Fault tolerance, error capture, and checkpoint resumption without re-running completed stages.
6. Dual-layer persistence at every stage boundary with cold-start recovery.
7. Fast, deterministic, 100% offline execution (< 2 seconds).
"""
from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path
from typing import Any

import pytest

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
from features.workflow.persistence_service import ProjectPersistenceService
from features.workflow.state_models import (
    PaperMetadata,
    ProjectState,
    utc_now,
)
from features.workflow.state_tools import (
    read_message_board,
    set_active_project_state,
)


@pytest.fixture
def isolated_persistence(tmp_path: Path) -> ProjectPersistenceService:
    """Provide an isolated persistence service with dedicated temporary storage."""
    base_dir = tmp_path / "data" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    service = ProjectPersistenceService(mysql=None, base_data_dir=base_dir)
    ProjectPersistenceService.set_instance(service)
    set_active_project_state(None)
    return service


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
# 1. Full Pipeline End-to-End Tests
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:
    """Verify full sequential execution across all 5 workflow stages."""

    @pytest.mark.asyncio
    async def test_full_pipeline_run_stages_1_through_5(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Full pipeline transitions cleanly through Stages 1 to 5 and completes project."""
        project = make_test_project("proj-e2e", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline("proj-e2e")

        # Project root status
        assert final_state.status == "completed"
        assert final_state.current_stage == "stage_5_export"
        assert final_state.completed_at is not None
        assert final_state.updated_at >= final_state.created_at

        # Verify every stage is completed with 100% progress
        for stage_name in STAGE_ORDER:
            substate = getattr(final_state, stage_name)
            assert substate.meta.status == "completed", f"Stage {stage_name} did not complete"
            assert substate.meta.progress_percentage == 100.0
            assert substate.meta.started_at is not None
            assert substate.meta.completed_at is not None
            assert substate.meta.completed_at >= substate.meta.started_at
            assert substate.meta.iteration_count >= 1
            assert substate.meta.error_message is None

        # Verify pipeline result
        assert pipeline.last_result is not None
        assert pipeline.last_result.success is True
        assert pipeline.last_result.status == "completed"
        assert len(pipeline.last_result.stages_executed) == 5
        assert pipeline.last_result.total_duration_seconds > 0.0

    @pytest.mark.asyncio
    async def test_full_pipeline_monotonic_timestamps_and_metrics(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Timestamps across sequential stages advance monotonically."""
        project = make_test_project("proj-mono")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(project)

        stages = [getattr(final_state, s) for s in STAGE_ORDER]
        for i in range(len(stages) - 1):
            assert stages[i].meta.started_at <= stages[i + 1].meta.started_at
            assert stages[i].meta.completed_at <= stages[i + 1].meta.completed_at

    @pytest.mark.asyncio
    async def test_lifecycle_callbacks_invoked(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Verify on_stage_start, on_stage_complete, and on_progress callbacks fire."""
        project = make_test_project("proj-cb")
        isolated_persistence.save_state(project)

        started_stages: list[str] = []
        completed_stages: list[str] = []
        progress_events: list[tuple[str, float, str]] = []

        async def on_start(stage: str, state: ProjectState) -> None:
            started_stages.append(stage)

        async def on_complete(stage: str, state: ProjectState) -> None:
            completed_stages.append(stage)

        async def on_prog(stage: str, pct: float, msg: str, state: ProjectState) -> None:
            progress_events.append((stage, pct, msg))

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        await pipeline.run_pipeline(
            "proj-cb",
            on_stage_start=on_start,
            on_stage_complete=on_complete,
            on_progress=on_prog,
        )

        assert started_stages == STAGE_ORDER
        assert completed_stages == STAGE_ORDER
        assert len(progress_events) >= 10


# ---------------------------------------------------------------------------
# 2. Stepwise Stage Progression & Prerequisites
# ---------------------------------------------------------------------------

class TestStepwiseStageProgression:
    """Verify single-stage execution, prerequisite guards, and stage aliases."""

    @pytest.mark.asyncio
    async def test_single_stage_stepwise_execution(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Executing an individual stage advances only that stage."""
        project = make_test_project("proj-stepwise")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        # 1. Run Stage 1
        s1_state = await pipeline.run_stage("proj-stepwise", "stage_1_research")
        assert s1_state.stage_1_research.meta.status == "completed"
        assert s1_state.stage_2_analysis.meta.status == "not_started"
        assert s1_state.stage_3_planning.meta.status == "not_started"
        assert s1_state.current_stage == "stage_1_research"

        # 2. Run Stage 2
        s2_state = await pipeline.run_stage("proj-stepwise", "stage_2_analysis")
        assert s2_state.stage_2_analysis.meta.status == "completed"
        assert s2_state.stage_3_planning.meta.status == "not_started"
        assert s2_state.current_stage == "stage_2_analysis"

        # 3. Run Stage 3
        s3_state = await pipeline.run_stage("proj-stepwise", "stage_3_planning")
        assert s3_state.stage_3_planning.meta.status == "completed"
        assert s3_state.stage_4_writing.meta.status == "not_started"

        # 4. Run Stage 4
        s4_state = await pipeline.run_stage("proj-stepwise", "stage_4_writing")
        assert s4_state.stage_4_writing.meta.status == "completed"
        assert s4_state.stage_5_export.meta.status == "not_started"

        # 5. Run Stage 5
        s5_state = await pipeline.run_stage("proj-stepwise", "stage_5_export")
        assert s5_state.stage_5_export.meta.status == "completed"
        assert s5_state.status == "completed"

    @pytest.mark.asyncio
    async def test_stepwise_stage_alias_and_numeric_resolution(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline resolves numeric ('1') and textual ('planning') aliases."""
        project = make_test_project("proj-alias")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        # Numeric '1' -> stage_1_research
        st1 = await pipeline.run_stage("proj-alias", "1")
        assert st1.stage_1_research.meta.status == "completed"

        # Textual 'analysis' -> stage_2_analysis
        st2 = await pipeline.run_stage("proj-alias", "analysis")
        assert st2.stage_2_analysis.meta.status == "completed"

        # Textual 'stage_3' -> stage_3_planning
        st3 = await pipeline.run_stage("proj-alias", "stage_3")
        assert st3.stage_3_planning.meta.status == "completed"

        # Numeric '4' -> stage_4_writing
        st4 = await pipeline.run_stage("proj-alias", "4")
        assert st4.stage_4_writing.meta.status == "completed"

        # Textual 'export' -> stage_5_export
        st5 = await pipeline.run_stage("proj-alias", "export")
        assert st5.stage_5_export.meta.status == "completed"

    @pytest.mark.asyncio
    async def test_unmet_prerequisite_stage_guard(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Calling a downstream stage on an uninitialized project raises ValueError."""
        project = make_test_project("proj-guard")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        # Attempting Stage 3 directly without Stage 1 or 2
        with pytest.raises(ValueError, match="prerequisite 'stage_2_analysis' is not completed"):
            await pipeline.run_stage("proj-guard", "stage_3_planning")

        # Attempting Stage 4 directly without Stage 3
        with pytest.raises(ValueError, match="has no section blueprints"):
            await pipeline.run_stage("proj-guard", "stage_4_writing")

    @pytest.mark.asyncio
    async def test_force_flag_bypasses_prerequisite_guard_and_re_executes(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """force=True re-executes completed stages and increments iteration_count."""
        project = make_test_project("proj-force")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_stage(project, "stage_1_research")
        assert state.stage_1_research.meta.iteration_count == 1

        # Re-run without force -> skipped
        state = await pipeline.run_stage(state, "stage_1_research", force=False)
        assert state.stage_1_research.meta.iteration_count == 1

        # Re-run with force -> executed again
        state = await pipeline.run_stage(state, "stage_1_research", force=True)
        assert state.stage_1_research.meta.iteration_count == 2


# ---------------------------------------------------------------------------
# 3. Inter-Stage Quadrant Hydration Tests
# ---------------------------------------------------------------------------

class TestInterStageQuadrantHydration:
    """Verify that artifacts from Stage N correctly hydrate inputs of Stage N+1."""

    @pytest.mark.asyncio
    async def test_stage_1_artifacts_hydrate_stage_2_analysis(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 1 papers and questions hydrate Stage 2 dimensions, clustering_k, and rankings."""
        project = make_test_project("proj-hydrate-1", seed_dois=["10.1145/3292500", "10.1016/j.artint.2024"])
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_stage(project, "stage_1_research")

        # Prior to Stage 2, clustering_k is None and target_dimensions is empty
        assert state.stage_2_analysis.inputs.clustering_k is None
        assert not state.stage_2_analysis.inputs.target_dimensions

        state = await pipeline.run_stage(state, "stage_2_analysis")

        s2 = state.stage_2_analysis
        assert s2.inputs.clustering_k is not None
        assert s2.inputs.clustering_k >= 2
        assert len(s2.inputs.target_dimensions) >= 4
        assert len(s2.artifacts.rankings) == len(state.stage_1_research.artifacts.papers)
        assert len(s2.artifacts.clusters) >= 2
        assert len(s2.artifacts.gaps) >= 1

    @pytest.mark.asyncio
    async def test_stage_2_artifacts_hydrate_stage_3_planning(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 2 clusters and gaps hydrate Stage 3 section blueprints and target section count."""
        project = make_test_project("proj-hydrate-2")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_stage(project, "stage_1_research")
        state = await pipeline.run_stage(state, "stage_2_analysis")
        state = await pipeline.run_stage(state, "stage_3_planning")

        s3 = state.stage_3_planning
        assert s3.inputs.target_section_count >= 4
        assert len(s3.artifacts.outline.sections) == s3.inputs.target_section_count
        assert len(s3.artifacts.section_blueprints) == len(s3.artifacts.outline.sections)

        # All assigned DOIs must be members of the Stage 1 paper library
        paper_dois = set(state.stage_1_research.artifacts.papers.keys())
        for sec in s3.artifacts.outline.sections:
            assert set(sec.assigned_dois).issubset(paper_dois)

        # DOI mappings map paper DOIs to section IDs
        assert len(s3.artifacts.doi_mappings) > 0
        for doi, sec_ids in s3.artifacts.doi_mappings.items():
            assert doi in paper_dois
            assert len(sec_ids) >= 1

    @pytest.mark.asyncio
    async def test_stage_3_artifacts_hydrate_stage_4_writing(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 3 outline sections hydrate Stage 4 section drafts drafting queue."""
        project = make_test_project("proj-hydrate-3")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_stage(project, "stage_1_research")
        state = await pipeline.run_stage(state, "stage_2_analysis")
        state = await pipeline.run_stage(state, "stage_3_planning")
        state = await pipeline.run_stage(state, "stage_4_writing")

        s4 = state.stage_4_writing
        outline_sections = state.stage_3_planning.artifacts.outline.sections

        for sec in outline_sections:
            assert sec.section_id in s4.artifacts.section_drafts
            draft = s4.artifacts.section_drafts[sec.section_id]
            assert draft.title == sec.title
            assert len(draft.markdown) > 50
            assert sec.section_id in s4.artifacts.section_reviews
            assert s4.artifacts.section_reviews[sec.section_id][0].approved is True

        assert len(s4.artifacts.full_draft_markdown) > 200
        assert s4.artifacts.citation_grounding_verified is True

    @pytest.mark.asyncio
    async def test_stage_4_artifacts_hydrate_stage_5_export(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 4 draft and paper library hydrate BibTeX entries, LaTeX files, and PDF outputs."""
        project = make_test_project("proj-hydrate-4")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_pipeline(project)

        s5 = state.stage_5_export
        assert len(s5.artifacts.bibtex_entries) == len(state.stage_1_research.artifacts.papers)
        assert s5.artifacts.tex_section_count == len(state.stage_4_writing.artifacts.section_drafts)

        # Validate file existence on disk
        tex_path = Path(s5.artifacts.tex_path)
        bib_path = Path(s5.artifacts.bib_path)
        pdf_path = Path(s5.artifacts.pdf_path)

        assert tex_path.exists()
        assert bib_path.exists()
        assert pdf_path.exists()

        assert "\\documentclass{article}" in tex_path.read_text(encoding="utf-8")
        assert "@article{" in bib_path.read_text(encoding="utf-8")
        assert pdf_path.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------------
# 4. Blackboard Coordination (Public Message Board)
# ---------------------------------------------------------------------------

class TestBlackboardCoordination:
    """Verify message posting across stages, querying, and isolated agent acknowledgment."""

    @pytest.mark.asyncio
    async def test_blackboard_cross_stage_message_posting(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """All stage runners publish typed discoveries to the shared message board."""
        project = make_test_project("proj-blackboard")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_pipeline("proj-blackboard")

        message_types = {m.message_type for m in state.message_board}
        # Core classification types specified in requirement R3
        assert {"insight", "serendipity", "gap", "warning", "decision", "hypothesis"}.issubset(message_types)

        # Author agents
        authors = {m.author_agent for m in state.message_board}
        assert {"ResearchAgent", "GapFinderAgent", "PlannerAgent", "WriterAgent"}.issubset(authors)

    @pytest.mark.asyncio
    async def test_downstream_stage_message_consumption_and_acknowledgment(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Downstream agents acknowledge board messages without clearing them for other agents."""
        project = make_test_project("proj-ack")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        # Run Stage 1 and 2
        state = await pipeline.run_stage(project, "stage_1_research")
        state = await pipeline.run_stage(state, "stage_2_analysis")

        # Locate the gap message posted by GapFinderAgent in Stage 2
        gap_msgs = [m for m in state.message_board if m.message_type == "gap"]
        assert len(gap_msgs) >= 1
        gap_msg = gap_msgs[0]

        # Prior to Stage 3: PlannerAgent and WriterAgent have NOT acknowledged it
        assert gap_msg.is_acknowledged_by("PlannerAgent") is False
        assert gap_msg.is_acknowledged_by("WriterAgent") is False

        # Run Stage 3 (PlannerAgent)
        state = await pipeline.run_stage(state, "stage_3_planning")

        # After Stage 3: PlannerAgent has acknowledged it; WriterAgent has NOT
        gap_msgs_after = [m for m in state.message_board if m.message_type == "gap"]
        assert gap_msgs_after[0].is_acknowledged_by("PlannerAgent") is True
        assert gap_msgs_after[0].is_acknowledged_by("WriterAgent") is False

        # Run Stage 4 (WriterAgent)
        state = await pipeline.run_stage(state, "stage_4_writing")

        # After Stage 4: WriterAgent has now acknowledged it
        gap_msgs_final = [m for m in state.message_board if m.message_type == "gap"]
        assert gap_msgs_final[0].is_acknowledged_by("WriterAgent") is True

    @pytest.mark.asyncio
    async def test_read_message_board_unacknowledged_filtering(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """read_message_board with unacknowledged_only filters accurately."""
        project = make_test_project("proj-unack-filter")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_stage(project, "stage_1_research")

        ctx = pipeline._create_stage_tool_context(state, "PlannerAgent")

        # Query unacknowledged for PlannerAgent (messages exist from Stage 1)
        res_before = await read_message_board(
            stage="stage_1_research",
            unacknowledged_only=True,
            unacknowledged_by="PlannerAgent",
            tool_context=ctx,
        )
        assert res_before["count"] >= 1

        # Now run Stage 2 and Stage 3 (which acknowledges them)
        state = await pipeline.run_stage(state, "stage_2_analysis")
        state = await pipeline.run_stage(state, "stage_3_planning")

        ctx_after = pipeline._create_stage_tool_context(state, "PlannerAgent")

        # Query again for PlannerAgent -> all prior Stage 1 messages acknowledged
        res_after = await read_message_board(
            stage="stage_1_research",
            unacknowledged_only=True,
            unacknowledged_by="PlannerAgent",
            tool_context=ctx_after,
        )
        assert res_after["count"] == 0


# ---------------------------------------------------------------------------
# 5. Failure Handling and Checkpoint Resumption
# ---------------------------------------------------------------------------

class TestFailureHandlingAndResumption:
    """Verify fault tolerance, failure capture, and non-redundant checkpoint resumption."""

    @pytest.mark.asyncio
    async def test_pipeline_stage_failure_preserves_prior_artifacts(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Injected stage failure captures error, posts warning, and preserves prior completed stages."""
        project = make_test_project("proj-fail")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        pipeline.set_stage_failure("stage_3_planning", RuntimeError("Simulated LLM API rate limit"))

        # Pipeline halts at Stage 3 with raise_on_error=False
        state = await pipeline.run_pipeline("proj-fail", raise_on_error=False)

        assert state.status == "failed"
        assert state.stage_1_research.meta.status == "completed"
        assert state.stage_2_analysis.meta.status == "completed"
        assert state.stage_3_planning.meta.status == "failed"
        assert "Simulated LLM API rate limit" in state.stage_3_planning.meta.error_message
        assert state.stage_4_writing.meta.status == "not_started"
        assert state.stage_5_export.meta.status == "not_started"

        # Board warning was published
        warnings = [m for m in state.message_board if m.message_type == "warning" and "stage_3_planning" in m.stage]
        assert len(warnings) >= 1
        assert "Simulated LLM API rate limit" in warnings[0].content

    @pytest.mark.asyncio
    async def test_pipeline_resumes_from_checkpoint_without_re_executing_prior_stages(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Resuming pipeline from checkpoint executes only uncompleted stages."""
        project = make_test_project("proj-resume")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        # 1. Fail at Stage 3
        pipeline.set_stage_failure("stage_3_planning", TimeoutError("Network timeout connecting to planner"))
        failed_state = await pipeline.run_pipeline("proj-resume", raise_on_error=False)
        assert failed_state.stage_3_planning.meta.status == "failed"

        # Check execution counts
        assert pipeline.get_stage_execution_count("stage_1_research") == 1
        assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
        assert pipeline.get_stage_execution_count("stage_3_planning") == 0  # Failed before runner execution

        # 2. Clear failure and resume from checkpoint
        pipeline.clear_stage_failure("stage_3_planning")
        resumed_state = await pipeline.run_pipeline("proj-resume", resume_from_checkpoint=True)

        assert resumed_state.status == "completed"
        assert resumed_state.stage_3_planning.meta.status == "completed"
        assert resumed_state.stage_4_writing.meta.status == "completed"
        assert resumed_state.stage_5_export.meta.status == "completed"

        # Crucial assertion: Stage 1 and Stage 2 were NOT re-executed!
        assert pipeline.get_stage_execution_count("stage_1_research") == 1
        assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
        assert pipeline.get_stage_execution_count("stage_3_planning") == 1
        assert pipeline.get_stage_execution_count("stage_4_writing") == 1
        assert pipeline.get_stage_execution_count("stage_5_export") == 1

    @pytest.mark.asyncio
    async def test_pipeline_stop_at_stage(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline respects start_stage and stop_at_stage parameters."""
        project = make_test_project("proj-stop-at")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        state = await pipeline.run_pipeline("proj-stop-at", start_stage="stage_1_research", stop_at_stage="stage_2_analysis")

        assert state.stage_1_research.meta.status == "completed"
        assert state.stage_2_analysis.meta.status == "completed"
        assert state.stage_3_planning.meta.status == "not_started"
        assert state.stage_4_writing.meta.status == "not_started"
        assert state.stage_5_export.meta.status == "not_started"


# ---------------------------------------------------------------------------
# 6. Persistence at Stage Transitions
# ---------------------------------------------------------------------------

class TestPersistenceAtStageTransitions:
    """Verify atomic disk writes at each stage milestone and cold recovery."""

    @pytest.mark.asyncio
    async def test_disk_json_updated_at_every_stage_transition(
        self, isolated_persistence: ProjectPersistenceService, tmp_path: Path
    ) -> None:
        """At every stage transition, project_state.json on disk is valid and reflects current progress."""
        project = make_test_project("proj-disk-sync")
        isolated_persistence.save_state(project)

        state_file = isolated_persistence.get_state_file_path("proj-disk-sync")
        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        for stage_name in STAGE_ORDER:
            await pipeline.run_stage("proj-disk-sync", stage_name)
            assert state_file.exists()

            # Read raw disk content
            raw_text = state_file.read_text(encoding="utf-8")
            data = json.loads(raw_text)

            assert data[stage_name]["meta"]["status"] == "completed"
            assert data[stage_name]["meta"]["progress_percentage"] == 100.0

            # Independent Pydantic deserialization
            reloaded = ProjectState.model_validate(data)
            assert reloaded.project_id == "proj-disk-sync"
            assert getattr(reloaded, stage_name).meta.status == "completed"

    @pytest.mark.asyncio
    async def test_cold_start_recovery_from_disk_after_pipeline_run(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Recovering state in a fresh pipeline instance without in-memory cache succeeds completely."""
        project = make_test_project("proj-cold-start")
        isolated_persistence.save_state(project)

        # Run pipeline to completion
        pipeline1 = WorkflowExecutionPipeline(persistence=isolated_persistence)
        await pipeline1.run_pipeline("proj-cold-start")

        # Simulate fresh cold-start (new pipeline, clean memory context)
        pipeline2 = WorkflowExecutionPipeline(persistence=isolated_persistence)
        cold_state = await pipeline2._resolve_state("proj-cold-start")

        assert cold_state.status == "completed"
        assert cold_state.current_stage == "stage_5_export"
        assert len(cold_state.stage_1_research.artifacts.papers) >= 2
        assert len(cold_state.stage_3_planning.artifacts.outline.sections) >= 3
        assert len(cold_state.stage_4_writing.artifacts.full_draft_markdown) > 100
        assert len(cold_state.stage_5_export.artifacts.bibtex_entries) >= 2


# ---------------------------------------------------------------------------
# 7. Offline Deterministic Performance & Speed Guarantee
# ---------------------------------------------------------------------------

class TestOfflineDeterministicPerformance:
    """Guarantee 100% offline portability and sub-2-second execution benchmark."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_strictly_offline_under_two_seconds(
        self, isolated_persistence: ProjectPersistenceService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pipeline runs 100% offline without socket calls and finishes in < 2 seconds."""
        # Block external network requests
        def forbid_network(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("External network connection attempted during offline test!")

        monkeypatch.setattr(socket.socket, "connect", forbid_network)

        project = make_test_project("proj-benchmark")
        isolated_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        start_time = time.perf_counter()
        final_state = await pipeline.run_pipeline("proj-benchmark")
        elapsed = time.perf_counter() - start_time

        assert final_state.status == "completed"
        assert elapsed < 2.0, f"Pipeline execution took {elapsed:.3f}s, exceeding 2.0s limit"

    @pytest.mark.asyncio
    async def test_convenience_functions_run_pipeline_and_run_stage(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Module-level run_pipeline and run_stage convenience functions execute cleanly."""
        project = make_test_project("proj-convenience")
        isolated_persistence.save_state(project)

        # run_stage convenience
        s1 = await run_stage("proj-convenience", "stage_1_research", persistence=isolated_persistence)
        assert s1.stage_1_research.meta.status == "completed"

        # run_pipeline convenience
        final = await run_pipeline("proj-convenience", persistence=isolated_persistence)
        assert final.status == "completed"
        assert final.stage_5_export.meta.status == "completed"
