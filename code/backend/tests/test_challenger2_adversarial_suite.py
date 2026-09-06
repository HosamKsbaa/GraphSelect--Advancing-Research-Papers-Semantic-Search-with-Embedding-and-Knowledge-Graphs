"""Adversarial Challenge Verification Suite (Challenger 2 Milestone 6).

Adversarially probes:
1. End-to-end 5-stage literature review scenario on "Agentic Workflows in Scientific Discovery"
   - Search query generation, BFS crawl citation edges, gap analysis, narrative blueprint,
     LaTeX drafting with grounded citations, BibTeX export with deduplicated citation keys.
2. Cold restart recovery with byte-for-byte quadrant fidelity
   - Process termination simulation, cache wipe, exact quadrant snapshot equality, and resumption.
3. Corrupted disk JSON recovery via MySQL fallback
   - Truncated JSON, binary garbage, invalid schema JSON, 0-byte file, MySQL fallback + disk repair,
     and unrecoverable state error handling.
4. Mid-stage failure error capture and non-redundant resumption
   - Interruption at Stage 2, Stage 3, and Stage 4; error capture in meta; warning broadcast on board;
     non-redundant resumption skipping completed stages; manual operator intervention.
5. Tier 3 Pairwise Combinations
   - Multi-agent handoff via ADK context, dot-path queries on complex mutated keys, token budget accounting.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import AsyncMock

import pytest

from features.workflow.execution_pipeline import (
    STAGE_ORDER,
    WorkflowExecutionPipeline,
    run_pipeline,
    run_stage,
)
from features.workflow.persistence_service import (
    ProjectPersistenceService,
    validate_project_id,
)
from features.workflow.state_models import (
    OutlineStructure,
    SectionDraft,
    PaperMetadata,
    ProjectState,
    SectionBlueprint,
    StageNote,
    normalize_doi,
    utc_now,
)
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
    set_active_project_state,
    update_stage_substate,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Mocks
# ---------------------------------------------------------------------------

class DummyAgent:
    def __init__(self, name: str = "ResearchAgent") -> None:
        self.name = name


class DummyToolContext:
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
    """In-memory mock of MySQL service for persistence testing."""
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


@pytest.fixture(autouse=True)
def offline_socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Enforce zero external network calls."""
    orig_connect = socket.socket.connect

    def _guarded_connect(self: socket.socket, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Network call blocked: offline test isolation enforced")

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield
    monkeypatch.setattr(socket.socket, "connect", orig_connect)


@pytest.fixture
def isolated_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "data" / "projects"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


@pytest.fixture
def isolated_persistence(isolated_storage: Path) -> ProjectPersistenceService:
    service = ProjectPersistenceService(mysql=None, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(service)
    set_active_project_state(None)
    return service


# ---------------------------------------------------------------------------
# Area 1: End-to-End 5-Stage Literature Review Scenario
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_challenge_e2e_5_stage_scientific_discovery(
    isolated_storage: Path,
) -> None:
    """Adversarially verify the full 5-stage literature review on Agentic Workflows in Scientific Discovery.

    Validates:
    - Normalization of messy seed DOIs (trailing spaces, URL prefix, mixed case).
    - Stage 1: Crawl queue, search queries, BFS citation edges, paper metadata.
    - Stage 2: Hybrid rankings (similarity, PageRank, hybrid formula), clusters, research gaps.
    - Stage 3: Narrative blueprint with section hierarchy, DOI assignments, DOI mappings without loss.
    - Stage 4: Grounded citation generation, Markdown section drafting, passing peer reviews.
    - Stage 5: Collision-free BibTeX entries, LaTeX document generation, mock PDF output.
    """
    mock_mysql = MockAsyncMySQL()
    service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(service)

    topic = "Agentic Workflows in Scientific Discovery: Autonomous Multi-Agent Systems for Hypothesis Generation, Literature Synthesis, and Laboratory Automation"
    # Seed DOIs with messy formatting to test normalization
    messy_seed_dois = [
        "https://doi.org/10.1038/s41586-023-06792-0",
        "  10.1126/SCIENCE.ADI1407  ",
        "10.1145/3292500",
        "doi:10.1016/j.artint.2024",
        "10.1109/TKDE.2023.101",
        "10.1145/3330964",
    ]
    research_questions = [
        "How do autonomous multi-agent systems coordinate in scientific discovery workflows?",
        "What are the key failure modes and citation hallucination risks in autonomous literature review pipelines?",
        "How can epistemic graph representations and verification checks enforce rigorous academic grounding?",
    ]

    proj = ProjectState(
        project_id="proj-e2e-adversarial-01",
        name="Agentic Scientific Discovery Review",
        topic=topic,
        target_level="phd",
        token_budget=1000000,
    )
    proj.stage_1_research.inputs.seed_dois = messy_seed_dois
    proj.stage_1_research.inputs.research_questions = research_questions
    await service.save_state_async(proj)

    pipeline = WorkflowExecutionPipeline(persistence=service)
    final_state = await pipeline.run_pipeline("proj-e2e-adversarial-01", raise_on_error=True)

    # 1. Stage 1 Research Verification
    assert final_state.stage_1_research.meta.status == "completed"
    papers = final_state.stage_1_research.artifacts.papers
    assert len(papers) >= 6

    # Verify DOI normalization occurred for all messy seed DOIs
    normalized_expected = [normalize_doi(d) for d in messy_seed_dois]
    for norm_doi in normalized_expected:
        assert norm_doi in papers, f"Expected normalized DOI {norm_doi} in papers library"
        assert papers[norm_doi].is_seed is True

    # Verify citation edges
    edges = final_state.stage_1_research.artifacts.citation_edges
    assert len(edges) >= 5
    for src, dst in edges:
        assert src in papers
        assert dst in papers

    # 2. Stage 2 Analysis Verification
    assert final_state.stage_2_analysis.meta.status == "completed"
    rankings = final_state.stage_2_analysis.artifacts.rankings
    assert len(rankings) == len(papers)
    for r in rankings:
        assert 0.0 <= r.similarity_score <= 1.0
        assert 0.0 <= r.pagerank_score <= 1.0
        assert 0.0 <= r.hybrid_score <= 1.0
        # Hybrid formula check
        expected_hybrid = round(
            r.similarity_score * final_state.stage_2_analysis.inputs.similarity_weight
            + r.pagerank_score * final_state.stage_2_analysis.inputs.pagerank_weight,
            3,
        )
        assert abs(r.hybrid_score - expected_hybrid) < 0.01

    clusters = final_state.stage_2_analysis.artifacts.clusters
    assert len(clusters) >= 2
    gaps = final_state.stage_2_analysis.artifacts.gaps
    assert len(gaps) >= len(research_questions)
    for gap in gaps:
        assert gap.severity in ("low", "medium", "high", "critical")
        assert len(gap.covered_by_dois) > 0

    # 3. Stage 3 Planning Verification
    assert final_state.stage_3_planning.meta.status == "completed"
    outline = final_state.stage_3_planning.artifacts.outline
    assert len(outline.sections) >= 4
    all_assigned_dois: set[str] = set()
    for s in outline.sections:
        assert s.target_word_count > 0
        assert len(s.assigned_dois) > 0
        all_assigned_dois.update(s.assigned_dois)

    # DOI mappings integrity
    doi_map = final_state.stage_3_planning.artifacts.doi_mappings
    for doi in all_assigned_dois:
        assert doi in doi_map
        assert len(doi_map[doi]) >= 1

    # 4. Stage 4 Writing Verification
    assert final_state.stage_4_writing.meta.status == "completed"
    drafts = final_state.stage_4_writing.artifacts.section_drafts
    assert len(drafts) == len(outline.sections)
    assert final_state.stage_4_writing.artifacts.citation_grounding_verified is True
    full_markdown = final_state.stage_4_writing.artifacts.full_draft_markdown
    assert len(full_markdown) > 500
    for s in outline.sections:
        assert s.section_id in drafts
        assert drafts[s.section_id].markdown is not None
        assert f"## {s.title}" in drafts[s.section_id].markdown

    # 5. Stage 5 Export Verification
    assert final_state.stage_5_export.meta.status == "completed"
    assert final_state.stage_5_export.artifacts.tex_path is not None
    assert final_state.stage_5_export.artifacts.bib_path is not None
    assert final_state.stage_5_export.artifacts.pdf_path is not None
    tex_path = Path(final_state.stage_5_export.artifacts.tex_path)
    bib_path = Path(final_state.stage_5_export.artifacts.bib_path)
    pdf_path = Path(final_state.stage_5_export.artifacts.pdf_path)

    assert tex_path.exists()
    assert bib_path.exists()
    assert pdf_path.exists()

    # Deep verification of LaTeX and BibTeX contents
    tex_content = tex_path.read_text(encoding="utf-8")
    bib_content = bib_path.read_text(encoding="utf-8")

    assert "\\documentclass{article}" in tex_content
    assert "\\begin{document}" in tex_content
    assert "\\end{document}" in tex_content
    assert "\\bibliography{references}" in tex_content

    # Verify BibTeX syntax and key collision-freedom
    assert bib_content.startswith("@article{")
    bib_keys = [line.split("{")[1].split(",")[0].strip() for line in bib_content.splitlines() if line.startswith("@article{")]
    assert len(bib_keys) == len(papers)
    assert len(set(bib_keys)) == len(bib_keys), "BibTeX keys must be unique without collisions"

    # Verify Root Completion
    assert final_state.status == "completed"
    assert final_state.completed_at is not None
    assert len(final_state.message_board) >= 5


# ---------------------------------------------------------------------------
# Area 2: Cold Restart Recovery with Byte-for-Byte Quadrant Fidelity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_cold_restart_quadrant_fidelity_and_continuation(
    isolated_storage: Path,
) -> None:
    """Stress-test cold restart recovery: verify byte-for-byte quadrant fidelity and continuation.

    Steps:
    1. Initialize pipeline, execute stages 1 through 3.
    2. Add rich data to all 4 quadrants (meta, inputs, artifacts, notes) across stages.
    3. Export pre-restart snapshot.
    4. Terminate process context (clear singletons, caches, references).
    5. Spin up fresh persistence and pipeline.
    6. Load state and verify exact JSON parity across all 4 quadrants of all completed stages.
    7. Execute stage 4 and 5 from recovered state and verify successful completion.
    """
    mock_mysql = MockAsyncMySQL()
    init_service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(init_service)

    proj = ProjectState(
        project_id="proj-cold-restart-adv-01",
        name="Cold Restart Resilience Review",
        topic="Self-Healing Multi-Agent Literature Synthesizers",
    )
    proj.stage_1_research.inputs.seed_dois = ["10.1145/3292500", "10.1016/j.artint.2024"]
    init_service.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=init_service)
    state_s3 = await pipeline.run_pipeline("proj-cold-restart-adv-01", stop_at_stage="stage_3_planning")

    # Add custom notes and metadata to test quadrant persistence fidelity
    state_s3.stage_1_research.notes.append(
        StageNote(author="ResearchAgent", content="Traversed 2 hops via OpenAlex polite pool.")
    )
    state_s3.stage_2_analysis.notes.append(
        StageNote(author="GapFinderAgent", content="Detected 3 distinct architectural gaps.")
    )
    state_s3.stage_3_planning.notes.append(
        StageNote(author="PlannerAgent", content="Crafted 4-part narrative arc.")
    )
    init_service.save_state(state_s3)

    # Capture exact serialized JSON snapshot before cold restart
    pre_snapshot = state_s3.model_dump(mode="json")

    # SIMULATE HARD RESTART: purge all in-memory references and singletons
    set_active_project_state(None)
    ProjectPersistenceService.set_instance(None)
    del state_s3
    del pipeline
    del init_service

    # Spin up fresh service from disk
    fresh_service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(fresh_service)
    fresh_pipeline = WorkflowExecutionPipeline(persistence=fresh_service)

    # Recover from disk
    recovered_state = await fresh_service.load_state("proj-cold-restart-adv-01")
    assert recovered_state is not None
    post_snapshot = recovered_state.model_dump(mode="json")

    # Exact quadrant fidelity checks: meta, inputs, artifacts, notes
    for st_name in ["stage_1_research", "stage_2_analysis", "stage_3_planning"]:
        assert pre_snapshot[st_name]["meta"] == post_snapshot[st_name]["meta"], f"{st_name}.meta mismatch"
        assert pre_snapshot[st_name]["inputs"] == post_snapshot[st_name]["inputs"], f"{st_name}.inputs mismatch"
        assert pre_snapshot[st_name]["artifacts"] == post_snapshot[st_name]["artifacts"], f"{st_name}.artifacts mismatch"
        assert pre_snapshot[st_name]["notes"] == post_snapshot[st_name]["notes"], f"{st_name}.notes mismatch"

    assert pre_snapshot["message_board"] == post_snapshot["message_board"]
    assert pre_snapshot["project_id"] == post_snapshot["project_id"]
    assert pre_snapshot["token_budget"] == post_snapshot["token_budget"]
    assert pre_snapshot["tokens_used"] == post_snapshot["tokens_used"]

    # Verify pipeline continuation from recovered state
    final_state = await fresh_pipeline.run_pipeline(recovered_state, start_stage="stage_4_writing")
    assert final_state.status == "completed"
    assert final_state.stage_4_writing.meta.status == "completed"
    assert final_state.stage_5_export.meta.status == "completed"
    assert final_state.stage_5_export.artifacts.tex_path is not None
    assert Path(final_state.stage_5_export.artifacts.tex_path).exists()


# ---------------------------------------------------------------------------
# Area 3: Corrupted Disk JSON Recovery via MySQL Fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_corrupted_disk_json_recovery_scenarios(
    isolated_storage: Path,
) -> None:
    """Stress-test corrupted disk JSON recovery via MySQL fallback across multiple corruption modes.

    Modes tested:
    1. Truncated unclosed JSON.
    2. Zero-byte empty file.
    3. Binary junk bytes (\x00\xff\xfe\xca\xfe).
    4. Invalid schema JSON (valid JSON syntax, invalid ProjectState structure).
    5. Double failure: Corrupted disk file AND missing MySQL record -> FileNotFoundError.
    """
    mock_mysql = MockAsyncMySQL()
    service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(service)

    # 1. Truncated JSON
    p1 = ProjectState(project_id="corrupt-truncated-01", name="Valid Truncated Project")
    p1.stage_1_research.artifacts.total_discovered = 88
    await service.save_state_async(p1)

    disk_path1 = service.get_state_file_path("corrupt-truncated-01")
    assert disk_path1.exists()
    disk_path1.write_bytes(b'{"project_id": "corrupt-truncated-01", "name": "Broken [EOF REACHED')

    set_active_project_state(None)
    rec1 = await service.load_state("corrupt-truncated-01")
    assert rec1 is not None
    assert rec1.project_id == "corrupt-truncated-01"
    assert rec1.stage_1_research.artifacts.total_discovered == 88
    # Assert disk file repaired
    assert json.loads(disk_path1.read_text(encoding="utf-8"))["project_id"] == "corrupt-truncated-01"

    # 2. Zero-byte empty file
    p2 = ProjectState(project_id="corrupt-zerobyte-02", name="Valid Zero-byte Project")
    p2.stage_2_analysis.artifacts.clusters = []
    await service.save_state_async(p2)

    disk_path2 = service.get_state_file_path("corrupt-zerobyte-02")
    disk_path2.write_bytes(b"")

    set_active_project_state(None)
    rec2 = await service.load_state("corrupt-zerobyte-02")
    assert rec2.project_id == "corrupt-zerobyte-02"
    assert disk_path2.stat().st_size > 0

    # 3. Binary junk bytes
    p3 = ProjectState(project_id="corrupt-binary-03", name="Valid Binary Junk Project")
    await service.save_state_async(p3)

    disk_path3 = service.get_state_file_path("corrupt-binary-03")
    disk_path3.write_bytes(bytes([0, 255, 254, 250, 128, 1, 2]) + b"GARBAGE_DATA_SEGMENT")

    set_active_project_state(None)
    rec3 = await service.load_state("corrupt-binary-03")
    assert rec3.project_id == "corrupt-binary-03"
    assert disk_path3.read_text(encoding="utf-8").startswith("{\n")

    # 4. Invalid schema JSON
    p4 = ProjectState(project_id="corrupt-schema-04", name="Valid Schema Project")
    await service.save_state_async(p4)

    disk_path4 = service.get_state_file_path("corrupt-schema-04")
    disk_path4.write_text('{"unknown_schema": true, "no_project_id": 123}', encoding="utf-8")

    set_active_project_state(None)
    rec4 = await service.load_state("corrupt-schema-04")
    assert rec4.project_id == "corrupt-schema-04"

    # 5. Double failure: Corrupted disk file AND missing MySQL record
    unrec_path = service.get_state_file_path("corrupt-unrecoverable-05")
    unrec_path.parent.mkdir(parents=True, exist_ok=True)
    unrec_path.write_bytes(b"CORRUPT")
    set_active_project_state(None)

    with pytest.raises(FileNotFoundError) as exc_info:
        await service.load_state("corrupt-unrecoverable-05")
    assert "not found" in str(exc_info.value).lower() or "unrecoverable" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Area 4: Mid-Stage Failure Error Capture and Non-Redundant Resumption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_mid_stage_failure_error_capture_and_non_redundant_resumption(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Stress-test failure capture and non-redundant resumption.

    Scenarios:
    1. Pipeline fails at Stage 2 with injected rate limit error.
    2. Verify error capture in Stage 2 meta and warning posted to message board.
    3. Verify Stage 1 is marked completed and not re-executed upon resume.
    4. Resume from checkpoint and verify Stage 2, 3, 4, 5 execute cleanly.
    5. Test manual operator intervention: Stage 3 fails, operator fixes artifacts via update_stage_substate,
       and resumption skips Stage 3 without redundant execution.
    """
    proj = ProjectState(project_id="proj-fail-resume-01", name="Mid-Stage Resilience")
    proj.stage_1_research.inputs.seed_dois = ["10.1145/3292500"]
    isolated_persistence.save_state(proj)

    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

    # 1. Inject failure at Stage 2
    pipeline.set_stage_failure("stage_2_analysis", ConnectionResetError("Remote API Connection Reset by Peer"))

    with pytest.raises(ConnectionResetError):
        await pipeline.run_pipeline("proj-fail-resume-01", raise_on_error=True)

    # 2. Validate error capture in state and message board
    failed_state = isolated_persistence.load_state_sync("proj-fail-resume-01")
    assert failed_state.status == "failed"
    assert failed_state.stage_1_research.meta.status == "completed"
    assert failed_state.stage_2_analysis.meta.status == "failed"
    assert "ConnectionResetError" in str(failed_state.stage_2_analysis.meta.error_message)

    # Verify failure notification on message board
    warn_msgs = [m for m in failed_state.message_board if m.message_type == "warning" and "stage_2_analysis" in m.tags]
    assert len(warn_msgs) >= 1
    assert "Remote API Connection Reset by Peer" in warn_msgs[0].content

    # Verify execution count: Stage 1 executed once, Stage 2 runner aborted before logic
    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 0

    # 3. Clear failure and resume from checkpoint
    pipeline.clear_stage_failure("stage_2_analysis")
    resumed_state = await pipeline.run_pipeline("proj-fail-resume-01", resume_from_checkpoint=True)

    # Invariant: Stage 1 was NOT re-executed (still 1), Stage 2 was executed (now 1)
    assert pipeline.get_stage_execution_count("stage_1_research") == 1
    assert pipeline.get_stage_execution_count("stage_2_analysis") == 1
    assert pipeline.get_stage_execution_count("stage_3_planning") == 1
    assert pipeline.get_stage_execution_count("stage_4_writing") == 1
    assert pipeline.get_stage_execution_count("stage_5_export") == 1
    assert resumed_state.status == "completed"

    # 4. Second Scenario: Manual Operator Intervention
    proj2 = ProjectState(project_id="proj-operator-int-02", name="Operator Intervention Test")
    proj2.stage_1_research.inputs.seed_dois = ["10.1145/3292500"]
    isolated_persistence.save_state(proj2)

    pipeline2 = WorkflowExecutionPipeline(persistence=isolated_persistence)
    # Execute stages 1 and 2
    await pipeline2.run_stage(proj2, "stage_1_research")
    await pipeline2.run_stage(proj2, "stage_2_analysis")

    # Inject failure at Stage 3
    pipeline2.set_stage_failure("stage_3_planning", TimeoutError("Outline generation timed out"))
    failed_state2 = await pipeline2.run_stage(proj2, "stage_3_planning", raise_on_error=False)
    assert failed_state2.stage_3_planning.meta.status == "failed"

    # Operator manually repairs Stage 3 using update_stage_substate
    ctx: Any = DummyToolContext(state={"project_state": failed_state2}, agent_name="SupervisorAgent")
    manual_outline = {
        "outline": {
            "title": "Operator Repaired Outline",
            "sections": [
                {"section_id": "sec-m1", "title": "Manual Section", "order": 1, "target_word_count": 1000}
            ],
        }
    }
    await update_stage_substate("stage_3_planning", "artifacts", manual_outline, tool_context=ctx)
    await update_stage_substate(
        "stage_3_planning", "meta", {"status": "completed", "error_message": None}, tool_context=ctx
    )

    pipeline2.clear_stage_failure("stage_3_planning")
    # Resume pipeline: since Stage 3 was marked completed by operator, pipeline should skip it!
    final_op_state = await pipeline2.run_pipeline("proj-operator-int-02", resume_from_checkpoint=True)

    assert pipeline2.get_stage_execution_count("stage_1_research") == 1
    assert pipeline2.get_stage_execution_count("stage_2_analysis") == 1
    assert pipeline2.get_stage_execution_count("stage_3_planning") == 0  # Skipped because operator completed it
    assert pipeline2.get_stage_execution_count("stage_4_writing") == 1
    assert pipeline2.get_stage_execution_count("stage_5_export") == 1
    assert final_op_state.status == "completed"


# ---------------------------------------------------------------------------
# Area 5: Pairwise Cross-Feature Interactions (Tier 3 Stress)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_pairwise_adk_agent_handoff_and_acknowledgment(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Pairwise: Verify multi-agent handoff across Research -> GapFinder -> Planner -> Writer.

    Validates:
    - ToolContext agent switching and attribution.
    - Public Message Board posting with typed classification and DOI grounding.
    - Granular acknowledgment tracking: filter by `unacknowledged_by` agent.
    - Scoped dot-path queries across stage boundaries.
    """
    proj = ProjectState(project_id="proj-pairwise-adv-01", name="Agent Handoff Verification")
    isolated_persistence.save_state(proj)

    ctx: Any = DummyToolContext(
        state={"project_state": proj, "project_id": proj.project_id},
        agent_name="ResearchAgent",
    )

    doi = "10.1038/s41586-023-06792-0"

    # Step 1: ResearchAgent posts insight
    res1 = await post_to_message_board(
        message_type="insight",
        title="Discovered Foundational Transformer Architecture",
        content="Autonomous synthesis discovered breakthrough architecture.",
        stage="stage_1_research",
        related_paper_dois=[doi],
        tool_context=ctx,
    )
    assert res1["status"] == "success"
    msg_id1 = res1["message_id"]

    # Step 2: GapFinderAgent reads insight, posts gap
    ctx.switch_agent("GapFinderAgent")
    read_res = await read_message_board(
        message_type="insight",
        unacknowledged_only=True,
        unacknowledged_by="GapFinderAgent",
        mark_as_acknowledged=True,
        tool_context=ctx,
    )
    assert read_res["count"] == 1
    assert read_res["messages"][0]["id"] == msg_id1

    res2 = await post_to_message_board(
        message_type="gap",
        title="Heterophily Coverage Deficit",
        content="Examined models show degradation on heterophilous graph topologies.",
        stage="stage_2_analysis",
        related_paper_dois=[doi],
        tool_context=ctx,
    )
    assert res2["status"] == "success"

    # Step 3: PlannerAgent acknowledges gap, posts outline decision
    ctx.switch_agent("PlannerAgent")
    gaps_unack = await read_message_board(
        message_type="gap",
        unacknowledged_by="PlannerAgent",
        mark_as_acknowledged=True,
        tool_context=ctx,
    )
    assert gaps_unack["count"] == 1

    blueprint = {
        "outline": {
            "title": "Synthesis Blueprint",
            "sections": [
                {"section_id": "sec-01", "order": 1, "title": "Overview", "target_word_count": 800}
            ],
        }
    }
    await update_stage_substate("stage_3_planning", "artifacts", blueprint, tool_context=ctx)
    res3 = await post_to_message_board(
        message_type="decision",
        title="Blueprint Approved",
        content="Outline approved with heterophily discussion section.",
        stage="stage_3_planning",
        tool_context=ctx,
    )
    assert res3["status"] == "success"

    # Step 4: WriterAgent queries outline title via dot-path and acknowledges decision
    ctx.switch_agent("WriterAgent")
    path_res = await get_project_state(
        scope="path",
        path="stage_3_planning.artifacts.outline.sections.0.title",
        tool_context=ctx,
    )
    assert path_res["status"] == "success"
    assert path_res["data"] == "Overview"

    dec_read = await read_message_board(
        message_type="decision",
        unacknowledged_by="WriterAgent",
        mark_as_acknowledged=True,
        tool_context=ctx,
    )
    assert dec_read["count"] == 1

    # Verify state board acknowledgment integrity
    state = ctx.state["project_state"]
    assert "GapFinderAgent" in state.message_board[0].acknowledged_by
    assert "PlannerAgent" in state.message_board[1].acknowledged_by
    assert "WriterAgent" in state.message_board[2].acknowledged_by


# ---------------------------------------------------------------------------
# Additional Adversarial Stress Tests: Edge Cases & Fault Modes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adversarial_pipeline_prerequisite_violations(
    isolated_persistence: ProjectPersistenceService,
) -> None:
    """Verify that execution pipeline strictly enforces stage prerequisite invariant rules."""
    proj = ProjectState(project_id="proj-prereq-viol-01", name="Prerequisite Violation")
    isolated_persistence.save_state(proj)
    pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

    # 1. Reversed sequence: start_stage after stop_at_stage
    with pytest.raises(ValueError) as exc_rev:
        await pipeline.run_pipeline("proj-prereq-viol-01", start_stage="stage_4_writing", stop_at_stage="stage_2_analysis")
    assert "occurs after" in str(exc_rev.value)

    # 2. Skip to Stage 4 Writing without Stage 3 Planning artifacts
    with pytest.raises(ValueError) as exc_s4:
        await pipeline.run_stage(proj, "stage_4_writing")
    assert "no section blueprints" in str(exc_s4.value)

    # 3. Skip to Stage 5 Export without Stage 4 Writing draft content
    with pytest.raises(ValueError) as exc_s5:
        await pipeline.run_stage(proj, "stage_5_export")
    assert "no draft content" in str(exc_s5.value)

    # 4. Skip to Stage 2 Analysis without Stage 1 papers
    with pytest.raises(ValueError) as exc_s2:
        await pipeline.run_stage(proj, "stage_2_analysis")
    assert "prerequisite 'stage_1_research' is not completed" in str(exc_s2.value)


@pytest.mark.asyncio
async def test_adversarial_corrupted_disk_and_mysql_db_failure(
    isolated_storage: Path,
) -> None:
    """Verify behavior when disk is corrupted AND MySQL raises an unhandled database exception."""
    mock_mysql = MockAsyncMySQL()
    # Force mysql.fetch_one to raise an exception
    async def _failing_fetch_one(sql: str, params: Any = None) -> Any:
        raise ConnectionRefusedError("MySQL connection pool exhausted (Errno 111)")

    mock_mysql.fetch_one = _failing_fetch_one  # type: ignore[assignment]
    service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)

    pid = "corrupt-db-fail-01"
    disk_path = service.get_state_file_path(pid)
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(b'{"corrupt": true, [EOF')

    with pytest.raises(FileNotFoundError) as exc_info:
        await service.load_state(pid)
    assert "database error" in str(exc_info.value).lower()
    assert "MySQL connection pool exhausted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_adversarial_concurrent_cold_cache_recovery_race(
    isolated_storage: Path,
) -> None:
    """Verify thread/asyncio safety when multiple concurrent tasks load a cold state simultaneously."""
    mock_mysql = MockAsyncMySQL()
    service = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=isolated_storage)

    state = ProjectState(project_id="concurrent-cold-01", name="Concurrent Cold Recovery")
    state.stage_1_research.artifacts.total_discovered = 150
    await service.save_state_async(state)

    # Wipe disk and in-memory caches to force MySQL fallback
    disk_file = service.get_state_file_path("concurrent-cold-01")
    disk_file.unlink()
    set_active_project_state(None)

    # Launch 20 concurrent loads of the cold state
    async def _load() -> ProjectState:
        return await service.load_state("concurrent-cold-01")

    tasks = [_load() for _ in range(20)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 20
    assert all(r.project_id == "concurrent-cold-01" for r in results)
    assert all(r.stage_1_research.artifacts.total_discovered == 150 for r in results)
    assert disk_file.exists()


@pytest.mark.asyncio
async def test_adversarial_bibtex_key_collision_stress_generation(
    isolated_storage: Path,
) -> None:
    """Stress test BibTeX key deduplication when many papers share identical author names and years."""
    service = ProjectPersistenceService(mysql=None, base_data_dir=isolated_storage)
    ProjectPersistenceService.set_instance(service)

    proj = ProjectState(project_id="proj-bib-collision-01", name="BibTeX Collision Test")
    # 30 papers with identical author "John Smith" and year 2024
    for i in range(30):
        doi = f"10.1145/collision.{i:03d}"
        proj.stage_1_research.artifacts.papers[doi] = PaperMetadata(
            doi=doi,
            title=f"Collision Paper Volume {i}",
            authors=["John Smith", "David Miller"],
            year=2024,
            citation_count=10,
        )

    # Outline and draft sections
    proj.stage_3_planning.artifacts.outline = OutlineStructure(
        title="Bib Collision Outline",
        sections=[
            SectionBlueprint(
                section_id="sec-01",
                title="1. Collisions",
                order=1,
                target_word_count=500,
                assigned_dois=list(proj.stage_1_research.artifacts.papers.keys()),
            )
        ],
    )
    proj.stage_4_writing.artifacts.section_drafts["sec-01"] = SectionDraft(section_id="sec-01", title="1. Collisions", markdown="## 1. Collisions\n\nContent text.")
    proj.stage_4_writing.artifacts.draft_sections_markdown["sec-01"] = "## 1. Collisions\n\nContent text."
    proj.stage_4_writing.artifacts.full_draft_markdown = "## 1. Collisions\n\nContent text."

    pipeline = WorkflowExecutionPipeline(persistence=service)
    state = await pipeline.run_stage(proj, "stage_5_export")

    bib_entries = state.stage_5_export.artifacts.bibtex_entries
    assert len(bib_entries) == 30

    bib_keys = [e.split("{")[1].split(",")[0].strip() for e in bib_entries]
    # Check that all 30 BibTeX keys are completely distinct
    assert len(set(bib_keys)) == 30
    assert bib_keys[0] == "smith2024"
    assert bib_keys[1] == "smith2024b"
    assert bib_keys[25] == "smith2024z"
    assert bib_keys[26] == "smith2024_26"  # Overflow suffix indexing beyond alphabet
