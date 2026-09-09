"""Empirical Adversarial Stress Test Suite for Milestone 5 (Requirement R6).

Author: Challenger 2 (Milestone 5)
Mission:
Adversarially challenge quadrant hydration, blackboard concurrency,
data fidelity, sparse inputs, blackboard deduplication & normalization,
isolated acknowledgment tracking, and irregular metadata export.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, cast
import pytest

from features.workflow.execution_pipeline import (
    AnalysisStageRunner,
    BaseStageRunner,
    ExportStageRunner,
    PipelineToolContext,
    PlanningStageRunner,
    ResearchStageRunner,
    STAGE_ORDER,
    StageExecutionResult,
    WorkflowExecutionPipeline,
    WritingStageRunner,
    run_pipeline,
    run_stage,
)
from features.workflow.persistence_service import ProjectPersistenceService
from features.workflow.state_models import (
    BoardMessage,
    OutlineStructure,
    PaperMetadata,
    ProjectState,
    SectionBlueprint,
    normalize_doi,
    utc_now,
)
from features.workflow.state_tools import (
    post_to_message_board,
    read_message_board,
    set_active_project_state,
)


@pytest.fixture
def isolated_persistence(tmp_path: Path) -> ProjectPersistenceService:
    """Isolated persistence service using dedicated temp directory."""
    base_dir = tmp_path / "data" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    service = ProjectPersistenceService(mysql=None, base_data_dir=base_dir)
    ProjectPersistenceService.set_instance(service)
    set_active_project_state(None)
    return service


# ==============================================================================
# 1. MINIMAL & SPARSE INITIAL INPUTS ADVERSARIAL SUITE
# ==============================================================================

class TestMinimalSparseInputs:
    """Challenge pipeline behavior when initial inputs are minimal, empty, or degenerate."""

    @pytest.mark.asyncio
    async def test_empty_research_questions_pipeline_execution(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline must succeed end-to-end even when research_questions list is completely empty."""
        state = ProjectState(
            project_id="proj-empty-rq",
            name="Empty RQ Review",
            topic="Topological Deep Learning",
            token_budget=100000,
        )
        state.stage_1_research.inputs.research_questions = []
        state.stage_1_research.inputs.keywords = ["topological deep learning"]
        state.stage_1_research.inputs.seed_dois = ["10.1145/3292500"]
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(state)

        assert final_state.status == "completed"
        # Stage 1 generates search queries using keywords or topic
        assert len(final_state.stage_1_research.artifacts.search_queries) > 0
        # Stage 2 synthesizes default coverage gaps when RQ is empty
        assert len(final_state.stage_2_analysis.artifacts.gaps) > 0
        assert final_state.stage_2_analysis.artifacts.gaps[0].question != ""
        # Downstream stages proceed cleanly
        assert final_state.stage_3_planning.meta.status == "completed"
        assert final_state.stage_4_writing.meta.status == "completed"
        assert final_state.stage_5_export.meta.status == "completed"

    @pytest.mark.asyncio
    async def test_empty_seed_dois_pipeline_execution(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline must fallback to synthetic domain seeds and complete when seed_dois is empty."""
        state = ProjectState(
            project_id="proj-empty-seeds",
            name="Zero Seeds Review",
            topic="Graph Neural Networks",
            token_budget=100000,
        )
        state.stage_1_research.inputs.seed_dois = []
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(state)

        assert final_state.status == "completed"
        papers = final_state.stage_1_research.artifacts.papers
        assert len(papers) >= 3, "Stage 1 should synthesize candidate seeds when seed_dois is empty"
        assert len(final_state.stage_1_research.artifacts.citation_edges) >= 2
        assert len(final_state.stage_2_analysis.artifacts.clusters) >= 2
        assert len(final_state.stage_3_planning.artifacts.outline.sections) >= 3
        assert len(final_state.stage_4_writing.artifacts.section_drafts) >= 3
        assert final_state.stage_5_export.artifacts.bibtex_entry_count >= 3

    @pytest.mark.asyncio
    async def test_single_paper_sparse_graph_execution(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Pipeline must survive and preserve data fidelity with exactly ONE seed paper and no edges."""
        single_doi = "10.1145/3292500"
        state = ProjectState(
            project_id="proj-single-paper",
            name="Single Paper Review",
            topic="Isolated Study",
            token_budget=100000,
        )
        state.stage_1_research.inputs.seed_dois = [single_doi]
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(state)

        assert final_state.status == "completed"
        papers = final_state.stage_1_research.artifacts.papers
        assert len(papers) == 1
        assert single_doi in papers
        # With 1 paper, citation_edges should be empty, avoiding out-of-bounds or self-loops
        assert final_state.stage_1_research.artifacts.citation_edges == []

        # Stage 2 clusters should handle single paper without zero-division
        clusters = final_state.stage_2_analysis.artifacts.clusters
        assert len(clusters) == 2
        for c in clusters:
            assert single_doi in c.paper_dois

        # Stage 3 outline should cover the single paper across sections
        sections = final_state.stage_3_planning.artifacts.outline.sections
        assert len(sections) >= 3
        doi_map = final_state.stage_3_planning.artifacts.doi_mappings
        assert single_doi in doi_map
        assert len(final_state.stage_3_planning.artifacts.unassigned_dois) == 0

        # Stage 4 writing should cite the single paper in drafted sections
        drafts = final_state.stage_4_writing.artifacts.section_drafts
        assert len(drafts) >= 3
        for d in drafts.values():
            assert len(d.cited_dois) >= 1

        # Stage 5 export should produce exactly 1 BibTeX entry
        assert final_state.stage_5_export.artifacts.bibtex_entry_count == 1
        assert Path(str(final_state.stage_5_export.artifacts.tex_path)).exists()
        assert Path(str(final_state.stage_5_export.artifacts.bib_path)).exists()
        assert Path(str(final_state.stage_5_export.artifacts.pdf_path)).exists()

    @pytest.mark.asyncio
    async def test_ultra_minimal_degenerate_state(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Ultra-minimal project with empty strings and empty lists."""
        state = ProjectState(
            project_id="proj-ultra-min",
            name="A",
            topic=None,
            token_budget=0,
        )
        state.stage_1_research.inputs.keywords = []
        state.stage_1_research.inputs.research_questions = []
        state.stage_1_research.inputs.seed_dois = []
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(state)

        assert final_state.status == "completed"
        assert len(final_state.stage_1_research.artifacts.search_queries) > 0
        assert final_state.stage_5_export.meta.status == "completed"


# ==============================================================================
# 2. BLACKBOARD CONCURRENCY, DEDUPLICATION & DOI NORMALIZATION SUITE
# ==============================================================================

class TestBlackboardDeduplicationAndNormalization:
    """Challenge blackboard message handling, canonical DOI normalization, and agent isolation."""

    @pytest.mark.parametrize("raw_doi, expected", [
        ("https://doi.org/10.1145/3292500", "10.1145/3292500"),
        ("http://dx.doi.org/10.1016/j.artint.2024", "10.1016/j.artint.2024"),
        ("doi: 10.1109/TKDE.2023.101", "10.1109/tkde.2023.101"),
        ("DOI:10.5555/TEST", "10.5555/test"),
        ("  10.1000/182  ", "10.1000/182"),
        ("///10.1234/slashes", "10.1234/slashes"),
        ("", ""),
        (None, ""),
    ])
    def test_canonical_doi_normalization_edge_cases(self, raw_doi: str | None, expected: str) -> None:
        """normalize_doi strips protocols, resolvers, prefixes, slashes, and downcases."""
        assert normalize_doi(raw_doi) == expected

    @pytest.mark.asyncio
    async def test_blackboard_doi_filtering_normalizes_queries(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """read_message_board with non-normalized DOI query should match normalized stored DOI."""
        state = ProjectState(project_id="proj-bb-norm", name="BB Norm")
        isolated_persistence.save_state(state)

        ctx: Any = PipelineToolContext("proj-bb-norm", state, "ResearchAgent")

        # Post message with prefixed DOI
        await post_to_message_board(
            message_type="insight",
            title="Discovery on GNN",
            content="GNN findings",
            stage="stage_1_research",
            related_paper_dois=["https://doi.org/10.1145/3292500"],
            tool_context=ctx,
        )

        # Stored DOI should be canonical
        assert state.message_board[0].related_paper_dois == ["10.1145/3292500"]

        # Query using a DIFFERENT dirty prefix
        res = await read_message_board(
            paper_doi="doi: 10.1145/3292500",
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["count"] == 1
        assert res["messages"][0]["title"] == "Discovery on GNN"

        # Query using uppercase URL
        res2 = await read_message_board(
            paper_doi="HTTPS://DOI.ORG/10.1145/3292500",
            tool_context=ctx,
        )
        assert res2["status"] == "success"
        assert res2["count"] == 1

    @pytest.mark.asyncio
    async def test_isolated_acknowledgment_tracking_across_agents(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Message acknowledgment must be strictly scoped to the active agent without leaking."""
        state = ProjectState(project_id="proj-ack-iso", name="Ack Isolation")
        isolated_persistence.save_state(state)

        ctx_res: Any = PipelineToolContext("proj-ack-iso", state, "ResearchAgent")
        ctx_plan: Any = PipelineToolContext("proj-ack-iso", state, "PlannerAgent")
        ctx_write: Any = PipelineToolContext("proj-ack-iso", state, "WriterAgent")

        # ResearchAgent posts gap
        await post_to_message_board(
            message_type="gap",
            title="Scalability Gap",
            content="Memory bottleneck in attention mechanism",
            stage="stage_2_analysis",
            tool_context=ctx_res,
        )

        msg = state.message_board[0]
        assert msg.acknowledged_by == []

        # PlannerAgent reads unacknowledged messages and acknowledges
        res_plan = await read_message_board(
            unacknowledged_only=True,
            mark_as_acknowledged=True,
            tool_context=ctx_plan,
        )
        assert res_plan["count"] == 1
        assert msg.is_acknowledged_by("PlannerAgent")
        assert not msg.is_acknowledged_by("WriterAgent")

        # PlannerAgent reading again with unacknowledged_only=True sees 0
        res_plan_2 = await read_message_board(
            unacknowledged_only=True,
            tool_context=ctx_plan,
        )
        assert res_plan_2["count"] == 0

        # WriterAgent reading with unacknowledged_only=True STILL SEES the message
        res_write = await read_message_board(
            unacknowledged_only=True,
            tool_context=ctx_write,
        )
        assert res_write["count"] == 1
        assert res_write["messages"][0]["id"] == msg.id

        # Calling acknowledge repeatedly for PlannerAgent does not create duplicates
        msg.acknowledge("PlannerAgent")
        msg.acknowledge("PlannerAgent")
        assert msg.acknowledged_by.count("PlannerAgent") == 1

    @pytest.mark.asyncio
    async def test_multi_agent_granular_acknowledgment_matrix(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Validate acknowledgment matrix across 4 different agents."""
        state = ProjectState(project_id="proj-multi-ack", name="Multi Ack Matrix")
        isolated_persistence.save_state(state)

        # Create 3 messages
        msg1 = state.post_message("AgentA", "insight", "Msg 1", "Content 1")
        msg2 = state.post_message("AgentA", "gap", "Msg 2", "Content 2")
        msg3 = state.post_message("AgentA", "warning", "Msg 3", "Content 3")

        # AgentB acknowledges msg1 and msg2
        msg1.acknowledge("AgentB")
        msg2.acknowledge("AgentB")

        # AgentC acknowledges only msg2
        msg2.acknowledge("AgentC")

        # Query unacknowledged for AgentB: only msg3
        ctx_b: Any = PipelineToolContext("proj-multi-ack", state, "AgentB")
        res_b = await read_message_board(unacknowledged_only=True, tool_context=ctx_b)
        assert [m["id"] for m in res_b["messages"]] == [msg3.id]

        # Query unacknowledged for AgentC: msg1 and msg3
        ctx_c: Any = PipelineToolContext("proj-multi-ack", state, "AgentC")
        res_c = await read_message_board(unacknowledged_only=True, tool_context=ctx_c)
        assert [m["id"] for m in res_c["messages"]] == [msg1.id, msg3.id]

        # Query unacknowledged for AgentD (acknowledged nothing): all 3
        ctx_d: Any = PipelineToolContext("proj-multi-ack", state, "AgentD")
        res_d = await read_message_board(unacknowledged_only=True, tool_context=ctx_d)
        assert len(res_d["messages"]) == 3

    @pytest.mark.asyncio
    async def test_blackboard_high_concurrency_posting(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Adversarially stress-test blackboard with 50 concurrent async postings."""
        state = ProjectState(project_id="proj-bb-stress", name="BB Concurrency Stress")
        isolated_persistence.save_state(state)

        async def post_task(idx: int) -> dict[str, Any]:
            ctx: Any = PipelineToolContext("proj-bb-stress", state, f"Agent-{idx % 5}")
            return await post_to_message_board(
                message_type="insight" if idx % 2 == 0 else "hypothesis",
                title=f"Concurrent Insight #{idx}",
                content=f"Detailed payload content for iteration {idx}",
                stage="stage_2_analysis",
                tags=[f"tag-{idx % 3}", "stress"],
                related_paper_dois=[f"10.1000/stress_{idx}"],
                tool_context=ctx,
            )

        # Launch 50 concurrent posts
        results = await asyncio.gather(*[post_task(i) for i in range(50)])

        assert len(results) == 50
        assert all(r["status"] == "success" for r in results)
        assert len(state.message_board) == 50

        # Check UUID uniqueness
        ids = [m.id for m in state.message_board]
        assert len(set(ids)) == 50, "All blackboard message IDs must be distinct UUIDs"

        # Concurrently read from multiple agents
        async def read_task(agent_id: int) -> dict[str, Any]:
            ctx: Any = PipelineToolContext("proj-bb-stress", state, f"Reader-{agent_id}")
            return await read_message_board(
                unacknowledged_only=True,
                limit=20,
                tool_context=ctx,
            )

        read_results = await asyncio.gather(*[read_task(i) for i in range(10)])
        assert all(r["status"] == "success" for r in read_results)
        assert all(r["count"] == 20 for r in read_results)

    @pytest.mark.asyncio
    async def test_duplicate_dois_in_message_payload_behavior(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Check behavior when duplicate DOIs with different formats are supplied to related_paper_dois."""
        state = ProjectState(project_id="proj-dup-dois", name="Dup DOIs Test")
        isolated_persistence.save_state(state)

        ctx: Any = PipelineToolContext("proj-dup-dois", state, "ResearchAgent")
        await post_to_message_board(
            message_type="insight",
            title="Duplicate DOIs in Payload",
            content="Testing duplicate DOIs",
            stage="stage_1_research",
            related_paper_dois=[
                "10.1145/3292500",
                "https://doi.org/10.1145/3292500",
                "doi: 10.1145/3292500",
            ],
            tool_context=ctx,
        )

        msg = state.message_board[0]
        # Document whether related_paper_dois preserves duplicates or deduplicates
        assert all(d == "10.1145/3292500" for d in msg.related_paper_dois)


# ==============================================================================
# 3. STAGE 5 EXPORT IRREGULAR METADATA ADVERSARIAL SUITE
# ==============================================================================

class TestExportStageIrregularMetadata:
    """Challenge Stage 5 export generation under irregular, missing, or malformed paper metadata."""

    @pytest.mark.asyncio
    async def test_export_with_missing_authors_empty_list(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """ExportStageRunner must handle papers where authors list is completely empty."""
        state = ProjectState(project_id="proj-no-author", name="Missing Author Review")
        state.stage_1_research.artifacts.papers["10.1234/no-auth"] = PaperMetadata(
            doi="10.1234/no-auth",
            title="Anonymous Contribution to Deep Learning",
            authors=[],
            year=2023,
        )
        state.stage_4_writing.artifacts.full_draft_markdown = "## Section 1\nDraft text citing [Ref, 2023]."
        state.stage_4_writing.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_stage(state, "stage_5_export")

        assert final_state.stage_5_export.meta.status == "completed"
        bib_entries = final_state.stage_5_export.artifacts.bibtex_entries
        assert len(bib_entries) == 1
        assert "author = {Unknown}" in bib_entries[0]
        assert "author2023" in bib_entries[0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blank_authors", [["   "], [""], ["\t\n  "]])
    async def test_export_and_writing_fail_on_whitespace_author_strings(
        self, isolated_persistence: ProjectPersistenceService, blank_authors: list[str]
    ) -> None:
        """REMEDIATION VERIFICATION: authors=['   '] or [''] safely handled in ExportStageRunner without IndexError."""
        state = ProjectState(project_id="proj-blank-author", name="Blank Author Review")
        state.stage_1_research.artifacts.papers["10.1234/blank-auth"] = PaperMetadata(
            doi="10.1234/blank-auth",
            title="Paper with Blank Author String",
            authors=blank_authors,
            year=2024,
        )
        state.stage_4_writing.artifacts.full_draft_markdown = "## Section 1\nDraft text."
        state.stage_4_writing.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        final_state = await pipeline.run_stage(state, "stage_5_export")
        assert final_state.stage_5_export.meta.status == "completed"
        assert len(final_state.stage_5_export.artifacts.bibtex_entries) == 1
        assert "author2024" in final_state.stage_5_export.artifacts.bibtex_entries[0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blank_authors", [["   "], [""], ["\t\n  "]])
    async def test_writing_stage_fails_on_whitespace_author_strings(
        self, isolated_persistence: ProjectPersistenceService, blank_authors: list[str]
    ) -> None:
        """REMEDIATION VERIFICATION: WritingStageRunner safely handles whitespace/empty authors without IndexError."""
        state = ProjectState(project_id="proj-blank-writing", name="Blank Author Writing Review")
        state.stage_1_research.artifacts.papers["10.1234/blank-auth"] = PaperMetadata(
            doi="10.1234/blank-auth",
            title="Paper with Blank Author String",
            authors=blank_authors,
            year=2024,
        )
        # Setup stage 3 outline assigning the paper
        state.stage_3_planning.artifacts.outline = OutlineStructure(
            title="Review",
            sections=[
                SectionBlueprint(
                    section_id="sec-01",
                    title="Section 1",
                    order=1,
                    level=1,
                    description="Desc",
                    assigned_dois=["10.1234/blank-auth"],
                )
            ],
        )
        state.stage_3_planning.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_stage(state, "stage_4_writing")
        assert final_state.stage_4_writing.meta.status == "completed"
        assert "sec-01" in final_state.stage_4_writing.artifacts.section_drafts
        assert "[Ref, 2024]" in final_state.stage_4_writing.artifacts.section_drafts["sec-01"].markdown

    @pytest.mark.asyncio
    async def test_bibtex_key_collision_adversarial_detection(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """REMEDIATION VERIFICATION: 5 papers with identical first author surname and year produces collision-free BibTeX keys."""
        state = ProjectState(project_id="proj-key-collision", name="Key Collision Review")

        # 5 distinct papers by authors with same surname in same year
        smith_names = ["Alice Smith", "Bob Smith", "Charlie Smith", "David Smith", "Eve Smith"]
        for idx, name in enumerate(smith_names, start=1):
            doi = f"10.1145/00{idx}"
            state.stage_1_research.artifacts.papers[doi] = PaperMetadata(
                doi=doi,
                title=f"Paper {idx} on Scalable Graph Networks",
                authors=[name],
                year=2024,
            )

        state.stage_4_writing.artifacts.full_draft_markdown = "## Section 1\nFull draft citing Smith papers."
        state.stage_4_writing.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_stage(state, "stage_5_export")

        assert final_state.stage_5_export.meta.status == "completed"
        bib_entries = final_state.stage_5_export.artifacts.bibtex_entries
        assert len(bib_entries) == 5

        # Extract BibTeX keys from entries: @article{key,
        keys: list[str] = []
        for entry in bib_entries:
            match = re.search(r"@article\{([^,]+),", entry)
            assert match is not None
            keys.append(match.group(1))

        # Ensure collision-free unique keys with sequential suffixes
        expected_keys = ["smith2024", "smith2024b", "smith2024c", "smith2024d", "smith2024e"]
        assert keys == expected_keys, (
            f"Expected collision-free disambiguated keys {expected_keys}, got {keys}"
        )
        assert len(set(keys)) == 5, "Collision-free confirmed: all 5 papers received unique keys"

    @pytest.mark.asyncio
    async def test_export_markdown_headings_converted_to_latex(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """REMEDIATION VERIFICATION: Markdown section headings are converted to LaTeX commands."""
        state = ProjectState(project_id="proj-md-latex", name="LaTeX Markdown Conversion Review")
        state.stage_4_writing.artifacts.full_draft_markdown = (
            "## Primary Methodology\nDiscussion text.\n\n### Experimental Results\nBenchmark text."
        )
        state.stage_4_writing.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_stage(state, "stage_5_export")

        assert final_state.stage_5_export.meta.status == "completed"
        tex_path = Path(str(final_state.stage_5_export.artifacts.tex_path))
        tex_content = tex_path.read_text(encoding="utf-8")

        assert "\\section{Primary Methodology}" in tex_content
        assert "\\subsection{Experimental Results}" in tex_content
        assert "## Primary Methodology" not in tex_content
        assert "### Experimental Results" not in tex_content

    @pytest.mark.asyncio
    async def test_create_stage_tool_context_attaches_agent_name(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """REMEDIATION VERIFICATION: _create_stage_tool_context attaches STAGE_AGENT_MAP[canonical_stage]."""
        state = ProjectState(project_id="proj-ctx-agent", name="Context Agent Test")
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)

        for stage, expected_agent in [
            ("stage_1_research", "ResearchAgent"),
            ("stage_2_analysis", "ResearchAgent"),
            ("stage_3_planning", "PlannerAgent"),
            ("stage_4_writing", "WriterAgent"),
            ("stage_5_export", "WriterAgent"),
        ]:
            ctx = pipeline._create_stage_tool_context(state, stage)
            assert ctx.agent_name == expected_agent
            assert ctx.state.get("agent_name") == expected_agent

    @pytest.mark.asyncio
    async def test_export_special_characters_handling(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Paper metadata and project title with LaTeX/BibTeX special characters (% & $ # _ { })."""
        state = ProjectState(
            project_id="proj-special-chars",
            name="Review of 100% SOTA & $O(N)$ {Graph} Models #1_beta",
        )
        state.stage_1_research.artifacts.papers["10.1145/spec-char"] = PaperMetadata(
            doi="10.1145/spec-char",
            title="A & B: 50% Speedup via $O(N)$ {Graph} #1 _methods_ \\ and ^powers^",
            authors=["René François", "Müller & Söhne"],
            year=2024,
        )
        state.stage_4_writing.artifacts.full_draft_markdown = (
            "## Section 1\nDiscussion on 100% convergence & complexity $O(V+E)$."
        )
        state.stage_4_writing.meta.status = "completed"
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_stage(state, "stage_5_export")

        assert final_state.stage_5_export.meta.status == "completed"
        bib_path = Path(str(final_state.stage_5_export.artifacts.bib_path))
        tex_path = Path(str(final_state.stage_5_export.artifacts.tex_path))

        assert bib_path.exists()
        assert tex_path.exists()
        bib_content = bib_path.read_text(encoding="utf-8")
        tex_content = tex_path.read_text(encoding="utf-8")

        assert "10.1145/spec-char" in bib_content
        # Confirm that raw unescaped LaTeX characters like '&' and '%' are present in document.tex
        assert "A & B" in bib_content or "A & B" in tex_content


# ==============================================================================
# 4. END-TO-END DATA FIDELITY ACROSS ALL 5 STAGES
# ==============================================================================

class TestEndToEndDataFidelity:
    """Verify that paper entities and metrics retain full fidelity from Stage 1 through Stage 5."""

    @pytest.mark.asyncio
    async def test_paper_doi_and_title_traceability_across_5_stages(
        self, isolated_persistence: ProjectPersistenceService
    ) -> None:
        """Every seed paper must be traceable across rankings, clusters, blueprints, drafts, and BibTeX."""
        test_seed = "10.1145/3292500"
        state = ProjectState(
            project_id="proj-fidelity",
            name="Data Fidelity Verification",
            topic="Graph Embeddings",
            token_budget=200000,
        )
        state.stage_1_research.inputs.seed_dois = [test_seed]
        isolated_persistence.save_state(state)

        pipeline = WorkflowExecutionPipeline(persistence=isolated_persistence)
        final_state = await pipeline.run_pipeline(state)

        # Stage 1: Seed paper exists in artifacts.papers
        s1_papers = final_state.stage_1_research.artifacts.papers
        assert test_seed in s1_papers
        expected_title = s1_papers[test_seed].title

        # Stage 2: Exists in rankings and findings
        s2_rankings = {r.doi: r for r in final_state.stage_2_analysis.artifacts.rankings}
        assert test_seed in s2_rankings
        assert s2_rankings[test_seed].title == expected_title

        s2_findings = final_state.stage_2_analysis.artifacts.findings_by_doi
        assert test_seed in s2_findings

        # Stage 3: Section blueprints assign the paper
        doi_map = final_state.stage_3_planning.artifacts.doi_mappings
        assert test_seed in doi_map
        assigned_sections = doi_map[test_seed]
        assert len(assigned_sections) > 0

        # Stage 4: Writing sections draft includes citation
        s4_drafts = final_state.stage_4_writing.artifacts.section_drafts
        cited = any(test_seed in draft.cited_dois for draft in s4_drafts.values())
        assert cited

        # Stage 5: BibTeX entries include the DOI
        s5_bib = final_state.stage_5_export.artifacts.bibtex_entries
        doi_in_bib = any(f"doi = {{{test_seed}}}" in entry for entry in s5_bib)
        assert doi_in_bib


# ==============================================================================
# 5. 5-RETRY HITL QUARANTINE SUSPENSION (Constitution A36 / Suggestion S2)
# ==============================================================================

class TestFiveRetryQuarantineSuspension:
    """Verify 5-retry limit, HITL quarantine suspension, and Neo4j quarantine record."""

    @pytest.mark.asyncio
    async def test_five_retry_rejection_triggers_quarantine_suspension(self, tmp_path: Path) -> None:
        """Simulate 5 consecutive rejections; verify awaiting_input, disk dump, and quarantine flag."""
        from features.workflow.execution_pipeline import execute_campaign
        from features.workflow.state_models import CritiqueVectorModel, ResearchCampaignModel

        campaign = ResearchCampaignModel(
            campaign_id="camp-quarantine-test",
            topic="Fault Tolerance in GNNs",
            entry_mode="refinement",
        )

        def mock_reject(st: int, it: int) -> CritiqueVectorModel:
            return CritiqueVectorModel(
                stage_index=st,
                critic_agent="ScopeBoundariesCritic",
                dimension="finer_compliance",
                measured_score=0.45,
                target_threshold=0.85,
                has_passed=False,
                violations=["RQ lacks non-inferiority margin."],
                actionable_directive="Add explicit margin.",
            )

        suspended = await execute_campaign(
            campaign, base_dir=tmp_path, simulate_critique=mock_reject
        )
        assert suspended.status == "awaiting_input"
        sub1 = suspended.substates[1]
        assert sub1.meta.is_quarantined is True
        assert sub1.meta.iteration_count == 5
        assert sub1.meta.quarantine_path is not None

        q_dir = tmp_path / "camp-quarantine-test" / "stage_1_rejected"
        assert q_dir.exists()
        dumped_file = q_dir / "rejected_iteration_5.json"
        assert dumped_file.exists()

    @pytest.mark.asyncio
    async def test_neo4j_quarantine_node_update(self, tmp_path: Path) -> None:
        """Verify Neo4j execute_write is called with StageSubstate quarantine cypher."""
        from unittest.mock import AsyncMock, MagicMock
        from features.workflow.execution_pipeline import apply_quarantine_suspension
        from features.workflow.state_models import ResearchCampaignModel, Stage1ScopingState

        campaign = ResearchCampaignModel(
            campaign_id="camp-neo4j-q", topic="Neo4j Persistence Test"
        )
        campaign.substates[1] = Stage1ScopingState()
        mock_neo4j = AsyncMock()
        mock_persistence = MagicMock()
        mock_persistence.neo4j = mock_neo4j

        q_path = await apply_quarantine_suspension(
            campaign, 1, {"mock_artifact": 123}, persistence=mock_persistence, base_dir=tmp_path
        )
        assert campaign.status == "awaiting_input"
        assert campaign.substates[1].meta.is_quarantined is True
        mock_neo4j.execute_write.assert_called_once()
        call_cypher = mock_neo4j.execute_write.call_args[0][0]
        assert "is_quarantined = true" in call_cypher

    @pytest.mark.asyncio
    async def test_successful_retry_within_limit_does_not_quarantine(self, tmp_path: Path) -> None:
        """Rejection on iteration 1 and 2, but passing on iteration 3 avoids quarantine."""
        from features.workflow.execution_pipeline import run_dialectical_stage
        from features.workflow.state_models import CritiqueVectorModel, ResearchCampaignModel

        campaign = ResearchCampaignModel(campaign_id="camp-recover", entry_mode="refinement")

        def mock_recover(st: int, it: int) -> CritiqueVectorModel:
            passed = it >= 3
            return CritiqueVectorModel(
                stage_index=st,
                critic_agent="Critic",
                dimension="quality",
                measured_score=0.90 if passed else 0.50,
                target_threshold=0.80,
                has_passed=passed,
                actionable_directive="Approved" if passed else "Retry",
            )

        success, cv = await run_dialectical_stage(
            campaign, 1, base_dir=tmp_path, simulate_critique=mock_recover
        )
        assert success is True
        assert cv is not None and cv.has_passed is True
        sub = campaign.substates[1]
        assert sub.meta.is_quarantined is False
        assert sub.meta.status == "completed"

