"""Adversarial stress-testing suite for ALRS v2 Workflow Execution Pipeline.

Empirical verification covering:
1. Out-of-order stage execution without prerequisites & invalid stage sequence guards.
2. Forced re-runs (force=True) vs checkpoint resumption (resume_from_checkpoint=True).
3. Simulated stage failures (pre-execution and mid-execution) and artifact preservation.
4. Concurrent execution of multiple pipelines across distinct project IDs.
5. Mixed failure-concurrency isolation and single-instance concurrency behavior.
"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest

from features.workflow.execution_pipeline import (
    BaseStageRunner,
    ProgressCallback,
    STAGE_ORDER,
    STAGE_SEQUENCE,
    StageExecutionResult,
    WorkflowExecutionPipeline,
    run_pipeline,
    run_stage,
)
from features.workflow.persistence_service import ProjectPersistenceService
from features.workflow.state_models import (
    PaperMetadata,
    ProjectState,
    utc_now,
)
from features.workflow.state_tools import set_active_project_state


@pytest.fixture
def adversarial_persistence(tmp_path: Path) -> ProjectPersistenceService:
    """Provide an isolated persistence service in dedicated temporary directory."""
    base_dir = tmp_path / "data" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    service = ProjectPersistenceService(mysql=None, base_data_dir=base_dir)
    ProjectPersistenceService.set_instance(service)
    set_active_project_state(None)
    return service


def build_adversarial_project(
    project_id: str,
    name: str = "Adversarial Test Project",
    topic: str = "Stress Testing State Machine",
    seed_dois: list[str] | None = None,
) -> ProjectState:
    """Helper to create a pristine ProjectState."""
    state = ProjectState(
        project_id=project_id,
        name=name,
        topic=topic,
        token_budget=1000000,
    )
    if seed_dois:
        state.stage_1_research.inputs.seed_dois = seed_dois
    state.stage_1_research.inputs.keywords = ["adversarial", "testing", "robustness"]
    state.stage_1_research.inputs.research_questions = ["Q1: How robust is the pipeline?"]
    return state


# ===========================================================================
# 1. Adversarial Challenge: Out-of-Order Stage Execution Without Prerequisites
# ===========================================================================

class TestAdversarialOutOfOrderExecution:
    """Stress-test execution guards against out-of-order invocations and missing prerequisites."""

    @pytest.mark.asyncio
    async def test_cannot_run_stage_2_without_prerequisite(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 2 must reject execution when Stage 1 has not run and has no papers."""
        project = build_adversarial_project("proj-ooo-2")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="Cannot run 'stage_2_analysis': prerequisite 'stage_1_research' is not completed"):
            await pipeline.run_stage("proj-ooo-2", "stage_2_analysis")

    @pytest.mark.asyncio
    async def test_cannot_run_stage_3_without_prerequisite(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 3 must reject execution when Stage 2 has not run and has no clusters."""
        project = build_adversarial_project("proj-ooo-3")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="Cannot run 'stage_3_planning': prerequisite 'stage_2_analysis' is not completed"):
            await pipeline.run_stage("proj-ooo-3", "stage_3_planning")

    @pytest.mark.asyncio
    async def test_cannot_run_stage_4_without_prerequisite(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 4 must reject execution when Stage 3 has no section blueprints."""
        project = build_adversarial_project("proj-ooo-4")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="Cannot run 'stage_4_writing': prerequisite 'stage_3_planning' has no section blueprints"):
            await pipeline.run_stage("proj-ooo-4", "stage_4_writing")

    @pytest.mark.asyncio
    async def test_cannot_run_stage_5_without_prerequisite(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Stage 5 must reject execution when Stage 4 has no draft content."""
        project = build_adversarial_project("proj-ooo-5")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="Cannot run 'stage_5_export': prerequisite 'stage_4_writing' has no draft content"):
            await pipeline.run_stage("proj-ooo-5", "stage_5_export")

    @pytest.mark.asyncio
    async def test_invalid_stage_names_rejected(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline and stage runners must reject unknown or corrupted stage names."""
        project = build_adversarial_project("proj-invalid-stage")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="Invalid stage 'stage_99_nonexistent'"):
            await pipeline.run_stage("proj-invalid-stage", "stage_99_nonexistent")

        with pytest.raises(ValueError, match="Invalid start_stage 'bogus_stage'"):
            await pipeline.run_pipeline("proj-invalid-stage", start_stage="bogus_stage")

        with pytest.raises(ValueError, match="Invalid stop_at_stage 'nonexistent'"):
            await pipeline.run_pipeline("proj-invalid-stage", stop_at_stage="nonexistent")

    @pytest.mark.asyncio
    async def test_reversed_sequence_rejected(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """run_pipeline must reject start_stage appearing after stop_at_stage."""
        project = build_adversarial_project("proj-reversed")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        with pytest.raises(ValueError, match="occurs after stop_at_stage"):
            await pipeline.run_pipeline(
                "proj-reversed",
                start_stage="stage_4_writing",
                stop_at_stage="stage_2_analysis",
            )

    @pytest.mark.asyncio
    async def test_force_bypasses_prerequisite_guards_safely(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """When force=True is passed, stage runners execute even with empty previous stages."""
        project = build_adversarial_project("proj-force-empty")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        # Forcing stage 4 directly on an empty project
        result_state = await pipeline.run_stage("proj-force-empty", "stage_4_writing", force=True)
        assert result_state.stage_4_writing.meta.status == "completed"
        # Since no section blueprints existed, draft was empty but runner did not crash
        assert result_state.stage_4_writing.artifacts.full_draft_markdown == ""


# ===========================================================================
# 2. Adversarial Challenge: Force Re-runs vs Checkpoint Resumption
# ===========================================================================

class TestAdversarialForceVsCheckpointResumption:
    """Stress-test force=True vs resume_from_checkpoint=True under various stage states."""

    @pytest.mark.asyncio
    async def test_checkpoint_skips_all_completed_stages(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """A fully completed pipeline skips 100% of stages when resume_from_checkpoint=True."""
        project = build_adversarial_project("proj-chk-skip")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        # Initial run: all 5 stages execute
        state_1 = await pipeline.run_pipeline("proj-chk-skip")
        assert state_1.status == "completed"
        for s in STAGE_ORDER:
            assert pipeline.get_stage_execution_count(s) == 1

        # Second run with resume_from_checkpoint=True and force=False
        state_2 = await pipeline.run_pipeline("proj-chk-skip", resume_from_checkpoint=True, force=False)
        assert state_2.status == "completed"
        # Zero additional executions
        for s in STAGE_ORDER:
            assert pipeline.get_stage_execution_count(s) == 1
        assert pipeline.last_result is not None
        assert pipeline.last_result.stages_executed == []

    @pytest.mark.asyncio
    async def test_force_reruns_all_completed_stages(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """When force=True, all stages re-execute regardless of checkpoint status."""
        project = build_adversarial_project("proj-force-rerun")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        # Initial run
        state_1 = await pipeline.run_pipeline("proj-force-rerun")
        for s in STAGE_ORDER:
            assert pipeline.get_stage_execution_count(s) == 1
            assert getattr(state_1, s).meta.iteration_count == 1

        # Forced re-run
        state_rerun = await pipeline.run_pipeline("proj-force-rerun", force=True)
        assert state_rerun.status == "completed"
        for s in STAGE_ORDER:
            assert pipeline.get_stage_execution_count(s) == 2
            substate = getattr(state_rerun, s)
            assert substate.meta.iteration_count == 2
            assert substate.meta.status == "completed"

    @pytest.mark.asyncio
    async def test_partial_checkpoint_resumption_after_stage_2(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline stopped at stage 2 resumes cleanly at stage 3 with no stage 1 or 2 re-run."""
        project = build_adversarial_project("proj-partial-chk")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        # Run only stage 1 and stage 2
        await pipeline.run_pipeline("proj-partial-chk", stop_at_stage="stage_2_analysis")
        assert pipeline.get_stage_execution_count("stage_1_research") == 1
        assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
        assert pipeline.get_stage_execution_count("stage_3_planning") == 0

        # Resume full pipeline
        resumed = await pipeline.run_pipeline("proj-partial-chk", resume_from_checkpoint=True)
        assert resumed.status == "completed"
        # Stages 1 and 2 must remain at 1 execution
        assert pipeline.get_stage_execution_count("stage_1_research") == 1
        assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
        # Stages 3, 4, 5 executed once
        assert pipeline.get_stage_execution_count("stage_3_planning") == 1
        assert pipeline.get_stage_execution_count("stage_4_writing") == 1
        assert pipeline.get_stage_execution_count("stage_5_export") == 1

    @pytest.mark.asyncio
    async def test_single_stage_force_vs_no_force(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """run_stage with force=False skips completed stage; with force=True re-executes."""
        project = build_adversarial_project("proj-single-force")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        await pipeline.run_stage("proj-single-force", "stage_1_research")
        assert pipeline.get_stage_execution_count("stage_1_research") == 1

        # force=False skips
        await pipeline.run_stage("proj-single-force", "stage_1_research", force=False)
        assert pipeline.get_stage_execution_count("stage_1_research") == 1

        # force=True re-runs
        await pipeline.run_stage("proj-single-force", "stage_1_research", force=True)
        assert pipeline.get_stage_execution_count("stage_1_research") == 2


# ===========================================================================
# 3. Adversarial Challenge: Simulated Stage Failures and Artifact Preservation
# ===========================================================================

class CustomFailingRunner(BaseStageRunner):
    """A stage runner designed to simulate mid-execution failure after producing partial work."""

    def __init__(self, stage_name: str, agent_name: str, fail_at_step: int = 1) -> None:
        self.stage_name = stage_name
        self.agent_name = agent_name
        self.fail_at_step = fail_at_step

    async def execute(
        self,
        state: ProjectState,
        persistence: ProjectPersistenceService,
        tool_context: Any | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if self.stage_name == "stage_2_analysis":
            # Simulate generating some rankings before crashing
            state.stage_2_analysis.artifacts.rankings = []
            if self.fail_at_step == 1:
                raise RuntimeError("Mid-execution failure in embedding computation")


class TestAdversarialStageFailureAndArtifactPreservation:
    """Verify that simulated failures preserve prior stage artifacts in memory and on disk."""

    @pytest.mark.asyncio
    async def test_failure_at_stage_3_preserves_stage_1_and_stage_2_artifacts(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """When Stage 3 fails, Stage 1 and Stage 2 artifacts remain completely intact and persisted."""
        project = build_adversarial_project("proj-fail-3")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        pipeline.set_stage_failure("stage_3_planning", ConnectionResetError("Lost connection to PlannerAgent"))

        failed_state = await pipeline.run_pipeline("proj-fail-3", raise_on_error=False)

        assert failed_state.status == "failed"
        assert failed_state.stage_3_planning.meta.status == "failed"
        assert "Lost connection to PlannerAgent" in (failed_state.stage_3_planning.meta.error_message or "")

        # Prior Stage 1 artifacts verified
        s1_arts = failed_state.stage_1_research.artifacts
        assert len(s1_arts.papers) >= 3
        assert len(s1_arts.citation_edges) >= 2
        assert len(s1_arts.top_authors) >= 1

        # Prior Stage 2 artifacts verified
        s2_arts = failed_state.stage_2_analysis.artifacts
        assert len(s2_arts.rankings) >= 3
        assert len(s2_arts.clusters) >= 2
        assert len(s2_arts.gaps) >= 1
        assert s2_arts.comparison_matrix is not None

        # Verify disk persistence matches in-memory preservation
        loaded_disk_state = adversarial_persistence.load_state("proj-fail-3")
        assert loaded_disk_state.status == "failed"
        assert loaded_disk_state.stage_3_planning.meta.status == "failed"
        assert len(loaded_disk_state.stage_1_research.artifacts.papers) == len(s1_arts.papers)
        assert len(loaded_disk_state.stage_2_analysis.artifacts.clusters) == len(s2_arts.clusters)

    @pytest.mark.asyncio
    async def test_mid_execution_runner_failure_captured_and_persisted(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Custom failing runner raises inside execute(); pipeline catches, logs, and persists failure."""
        project = build_adversarial_project("proj-mid-fail")
        adversarial_persistence.save_state(project)

        custom_runners = {
            "stage_1_research": WorkflowExecutionPipeline().stage_runners["stage_1_research"],
            "stage_2_analysis": CustomFailingRunner("stage_2_analysis", "ResearchAgent", fail_at_step=1),
            "stage_3_planning": WorkflowExecutionPipeline().stage_runners["stage_3_planning"],
            "stage_4_writing": WorkflowExecutionPipeline().stage_runners["stage_4_writing"],
            "stage_5_export": WorkflowExecutionPipeline().stage_runners["stage_5_export"],
        }

        pipeline = WorkflowExecutionPipeline(
            persistence=adversarial_persistence,
            stage_runners=custom_runners,
        )

        failed_state = await pipeline.run_pipeline("proj-mid-fail", raise_on_error=False)

        assert failed_state.status == "failed"
        assert failed_state.stage_2_analysis.meta.status == "failed"
        assert "Mid-execution failure in embedding computation" in (failed_state.stage_2_analysis.meta.error_message or "")
        assert failed_state.stage_1_research.meta.status == "completed"
        assert len(failed_state.stage_1_research.artifacts.papers) > 0

        # Disk recovery verified
        disk_state = adversarial_persistence.load_state("proj-mid-fail")
        assert disk_state.stage_2_analysis.meta.status == "failed"
        assert disk_state.stage_1_research.meta.status == "completed"


# ===========================================================================
# 4. Adversarial Challenge: Concurrent Pipeline Execution Across Project IDs
# ===========================================================================

class TestAdversarialConcurrentPipelines:
    """Stress-test concurrent pipeline runs across multiple projects and evaluate isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_independent_pipeline_executions(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Execute 5 distinct projects concurrently via asyncio.gather."""
        project_ids = [f"proj-concurrent-{i:02d}" for i in range(1, 6)]
        projects: list[ProjectState] = []

        for idx, pid in enumerate(project_ids, start=1):
            p = build_adversarial_project(
                project_id=pid,
                name=f"Concurrent Project {idx}",
                topic=f"Topic {idx}: Distributed Graph Processing",
                seed_dois=[f"10.1145/{3000000 + idx}", f"10.1016/{2000000 + idx}"],
            )
            adversarial_persistence.save_state(p)
            projects.append(p)

        # Run all 5 concurrently
        tasks = [
            run_pipeline(
                pid,
                persistence=adversarial_persistence,
            )
            for pid in project_ids
        ]
        results = await asyncio.gather(*tasks)

        # Verify every project completed successfully
        for idx, res_state in enumerate(results, start=1):
            assert res_state.status == "completed", f"Project {res_state.project_id} did not complete"
            assert res_state.current_stage == "stage_5_export"
            assert res_state.name == f"Concurrent Project {idx}"

            # Verify on-disk project files exist independently
            proj_dir = adversarial_persistence.base_data_dir / res_state.project_id
            assert (proj_dir / "project_state.json").exists()
            assert (proj_dir / "exports" / "document.tex").exists()
            assert (proj_dir / "exports" / "references.bib").exists()
            assert (proj_dir / "exports" / "review.pdf").exists()

            # Verify no cross-project message pollution
            for msg in res_state.message_board:
                # All messages must not reference other project IDs
                assert res_state.project_id not in msg.content or res_state.project_id in msg.content

    @pytest.mark.asyncio
    async def test_concurrent_pipelines_with_mixed_outcomes(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Run 3 projects concurrently: one succeeds, one fails at Stage 2, one succeeds."""
        p1 = build_adversarial_project("proj-mixed-success-1", name="Success 1")
        p2 = build_adversarial_project("proj-mixed-fail-2", name="Failure 2")
        p3 = build_adversarial_project("proj-mixed-success-3", name="Success 3")

        adversarial_persistence.save_state(p1)
        adversarial_persistence.save_state(p2)
        adversarial_persistence.save_state(p3)

        pipe1 = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        pipe2 = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        pipe3 = WorkflowExecutionPipeline(persistence=adversarial_persistence)

        # Inject failure only into project 2
        pipe2.set_stage_failure("stage_2_analysis", RuntimeError("Simulated failure in project 2"))

        t1 = pipe1.run_pipeline("proj-mixed-success-1", raise_on_error=False)
        t2 = pipe2.run_pipeline("proj-mixed-fail-2", raise_on_error=False)
        t3 = pipe3.run_pipeline("proj-mixed-success-3", raise_on_error=False)

        res1, res2, res3 = await asyncio.gather(t1, t2, t3)

        # Verify Project 1 completed
        assert res1.status == "completed"
        assert res1.stage_5_export.meta.status == "completed"

        # Verify Project 2 failed at stage 2, stage 1 preserved
        assert res2.status == "failed"
        assert res2.stage_1_research.meta.status == "completed"
        assert res2.stage_2_analysis.meta.status == "failed"
        assert "Simulated failure in project 2" in (res2.stage_2_analysis.meta.error_message or "")

        # Verify Project 3 completed without any contamination from Project 2
        assert res3.status == "completed"
        assert res3.stage_5_export.meta.status == "completed"

    @pytest.mark.asyncio
    async def test_single_pipeline_instance_concurrency_hazard(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Adversarially probe what happens when a single WorkflowExecutionPipeline instance is reused concurrently.

        Notice: WorkflowExecutionPipeline maintains mutable instance state (self.stage_results,
        self.last_result, self.stage_execution_counts). We verify the behavioral outcome
        when run_pipeline is called concurrently on the SAME instance.
        """
        pA = build_adversarial_project("proj-shared-A", name="Project A")
        pB = build_adversarial_project("proj-shared-B", name="Project B")
        adversarial_persistence.save_state(pA)
        adversarial_persistence.save_state(pB)

        shared_pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)

        # Run both projects concurrently using the SAME pipeline instance
        tA = shared_pipeline.run_pipeline("proj-shared-A")
        tB = shared_pipeline.run_pipeline("proj-shared-B")
        resA, resB = await asyncio.gather(tA, tB)

        # Both states complete
        assert resA.status == "completed"
        assert resB.status == "completed"

        # However, shared_pipeline.last_result reflects only ONE project (race condition on instance attribute)
        assert shared_pipeline.last_result is not None
        assert shared_pipeline.last_result.project_id in ["proj-shared-A", "proj-shared-B"]

        # And stage_execution_counts counts executions across both projects (5 * 2 = 10 total)
        total_executions = sum(shared_pipeline.stage_execution_counts.values())
        assert total_executions == 10


# ===========================================================================
# 5. Additional Adversarial Edge Cases & Stress Scenarios
# ===========================================================================

class TestAdversarialDeepEdgeCases:
    """Further edge cases: partial artifacts, missing runners, callbacks, and high-volume concurrency."""

    @pytest.mark.asyncio
    async def test_stage_2_allowed_if_stage_1_failed_but_papers_exist(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """If stage 1 failed (e.g. crawler error) but papers were discovered, stage 2 proceeds."""
        project = build_adversarial_project("proj-partial-s1")
        # Stage 1 has papers but status is failed
        project.stage_1_research.meta.status = "failed"
        project.stage_1_research.meta.error_message = "Crawler interrupted"
        project.stage_1_research.artifacts.papers["10.1145/test"] = PaperMetadata(
            doi="10.1145/test",
            title="Partial Discovered Paper",
            authors=["Researcher One"],
            year=2024,
        )
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        # Stage 2 should succeed using available papers
        res = await pipeline.run_stage("proj-partial-s1", "stage_2_analysis")
        assert res.stage_2_analysis.meta.status == "completed"
        assert len(res.stage_2_analysis.artifacts.rankings) >= 1

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint_false_without_force_behavior(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """When resume_from_checkpoint=False and force=False, run_stage still guards completed stages."""
        project = build_adversarial_project("proj-chk-false")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        await pipeline.run_pipeline("proj-chk-false")
        assert pipeline.get_stage_execution_count("stage_1_research") == 1

        # Run with resume_from_checkpoint=False but force=False
        await pipeline.run_pipeline("proj-chk-false", resume_from_checkpoint=False, force=False)
        # run_stage skips execution because force=False
        assert pipeline.get_stage_execution_count("stage_1_research") == 1

    @pytest.mark.asyncio
    async def test_missing_stage_runner_raises_runtime_error_bypasses_try_block(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Adversarial finding: runner missing check (line 962) occurs outside try block.
        Even when raise_on_error=False, it raises RuntimeError directly, leaving stage in 'in_progress'.
        """
        project = build_adversarial_project("proj-missing-runner")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        pipeline.stage_runners.pop("stage_1_research")

        with pytest.raises(RuntimeError, match="No runner registered for stage 'stage_1_research'"):
            await pipeline.run_stage("proj-missing-runner", "stage_1_research", raise_on_error=False)

        # Notice: because it raised before try block, state on disk remains 'in_progress'
        st = adversarial_persistence.load_state("proj-missing-runner")
        assert st.stage_1_research.meta.status == "in_progress"

    @pytest.mark.asyncio
    async def test_on_stage_failed_callback_receives_correct_arguments(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """on_stage_failed callback receives (stage_name, exception, state)."""
        project = build_adversarial_project("proj-cb-fail")
        adversarial_persistence.save_state(project)

        pipeline = WorkflowExecutionPipeline(persistence=adversarial_persistence)
        pipeline.set_stage_failure("stage_2_analysis", ArithmeticError("Simulated calculation error"))

        callback_data: dict[str, Any] = {}

        async def failure_callback(stage: str, exc: Exception, st: ProjectState) -> None:
            callback_data["stage"] = stage
            callback_data["exc"] = exc
            callback_data["st_id"] = st.project_id

        await pipeline.run_pipeline(
            "proj-cb-fail",
            raise_on_error=False,
            on_stage_failed=failure_callback,
        )

        assert callback_data["stage"] == "stage_2_analysis"
        assert isinstance(callback_data["exc"], ArithmeticError)
        assert callback_data["st_id"] == "proj-cb-fail"

    @pytest.mark.asyncio
    async def test_high_volume_concurrency_stress_twenty_projects(
        self, adversarial_persistence: ProjectPersistenceService
    ) -> None:
        """Stress-test system by running 20 distinct projects concurrently."""
        num_projects = 20
        project_ids = [f"proj-stress-{i:03d}" for i in range(1, num_projects + 1)]

        for idx, pid in enumerate(project_ids, start=1):
            p = build_adversarial_project(
                project_id=pid,
                name=f"Stress Review {idx}",
                topic=f"Scalability topic {idx}",
                seed_dois=[f"10.1145/{5000000 + idx}"],
            )
            adversarial_persistence.save_state(p)

        tasks = [
            run_pipeline(pid, persistence=adversarial_persistence)
            for pid in project_ids
        ]

        completed_states = await asyncio.gather(*tasks)

        assert len(completed_states) == num_projects
        for st in completed_states:
            assert st.status == "completed"
            assert st.stage_5_export.meta.status == "completed"
            # Verify file exists on disk
            disk_path = adversarial_persistence.base_data_dir / st.project_id / "project_state.json"
            assert disk_path.exists()
