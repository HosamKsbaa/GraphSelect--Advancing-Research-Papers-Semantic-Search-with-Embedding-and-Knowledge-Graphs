"""Comprehensive unit tests for Scoped Navigation & State Mutation Tools (Requirement R4).

Verifies:
- Tool execution with DummyToolContext containing ProjectState and raw dict states.
- get_project_state: summary mode, stage extraction, dot-path extraction, invalid paths returning error.
- post_to_message_board: successful posts across all 6 message types, DOI normalization, invalid type rejection.
- read_message_board: filtering by type, stage, tag, DOI, and unacknowledged status.
- update_stage_substate: mutating meta, inputs, artifacts, notes, deep-merge preservation, invalid stage/quadrant rejection.
"""
from __future__ import annotations

import pytest
from typing import Any

from features.workflow.state_models import (
    BoardClassification,
    BoardMessage,
    PaperMetadata,
    ProjectState,
    ResearchArtifacts,
    ResearchInputs,
    SectionBlueprint,
    StageMeta,
    StageNote,
    normalize_doi,
)
from features.workflow.state_tools import (
    deep_merge,
    get_project_state,
    get_stage_status,
    post_to_message_board,
    read_message_board,
    set_active_project_state,
    transition_to_stage,
    update_stage_substate,
)


# ---------------------------------------------------------------------------
# Test Helpers: DummyToolContext and DummyAgent
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


@pytest.fixture(autouse=True)
def cleanup_active_state() -> None:
    """Reset module-level active state between test cases."""
    set_active_project_state(None)


def create_populated_project() -> ProjectState:
    """Create a fully populated ProjectState for navigation and filtering tests."""
    project = ProjectState(
        name="Scalable GNN Literature Review",
        topic="Graph Neural Networks and Inductive Representation Learning",
        token_budget=600000,
        tokens_used=12500,
    )

    # Populate Stage 1 (Research)
    doi_1 = "10.1145/3292500.3330964"
    doi_2 = "10.1016/j.artint.2024.103342"
    project.stage_1_research.meta.status = "completed"
    project.stage_1_research.meta.agent_name = "ALRSAgent"
    project.stage_1_research.meta.progress_percentage = 100.0

    project.stage_1_research.inputs.research_questions = [
        "What are the primary computational bottlenecks of Message Passing Neural Networks?",
        "How do sub-graph sampling methods mitigate neighborhood explosion?",
    ]
    project.stage_1_research.inputs.seed_dois = [doi_1]
    project.stage_1_research.inputs.max_depth = 2

    project.stage_1_research.artifacts.papers[doi_1] = PaperMetadata(
        doi=doi_1,
        title="Inductive Representation Learning on Large Graphs (GraphSAGE)",
        authors=["William L. Hamilton", "Rex Ying", "Jure Leskovec"],
        year=2017,
        citation_count=18500,
        is_seed=True,
    )
    project.stage_1_research.artifacts.papers[doi_2] = PaperMetadata(
        doi=doi_2,
        title="A Survey on Scalable Graph Neural Networks",
        authors=["Z. Liu", "Y. Zhou"],
        year=2024,
        citation_count=42,
    )

    # Populate Stage 3 (Planning) with outline sections
    project.stage_3_planning.meta.status = "in_progress"
    project.stage_3_planning.artifacts.outline.sections = [
        SectionBlueprint(
            title="Introduction to Graph Representation Learning",
            order=1,
            level=1,
            target_word_count=1200,
            assigned_dois=[doi_1],
        ),
        SectionBlueprint(
            title="Message Passing Paradigms and Over-smoothing",
            order=2,
            level=1,
            target_word_count=2000,
            assigned_dois=[doi_1, doi_2],
        ),
    ]

    # Populate Public Message Board
    project.post_message(
        author_agent="ALRSAgent",
        message_type="serendipity",
        title="Discovered Physics-Informed Graph Attention",
        content="Unexpected application of Hamiltonian ODEs to graph diffusion.",
        stage="stage_1_research",
        tags=["gnn", "diffusion", "physics"],
        related_paper_dois=[doi_2],
    )
    project.post_message(
        author_agent="GapFinderAgent",
        message_type="gap",
        title="Zero Empirical Benchmarks on Mobile Edge Hardware",
        content="None of the 45 crawled papers report inference latency on edge NPUs.",
        stage="stage_2_analysis",
        tags=["benchmarking", "hardware", "edge"],
    )
    project.post_message(
        author_agent="ReviewerAgent",
        message_type="warning",
        title="Inconsistent Memory Complexity Claims",
        content="Paper A claims O(N) memory while Paper B proves O(N^2) on dense graphs.",
        stage="stage_4_writing",
        tags=["complexity", "memory"],
        related_paper_dois=[doi_1, doi_2],
    )

    return project


# ---------------------------------------------------------------------------
# 1. DummyToolContext & State Resolution Tests
# ---------------------------------------------------------------------------

class TestStateResolution:
    """Test state resolution with ProjectState models, raw dicts, and fallbacks."""

    @pytest.mark.asyncio
    async def test_execution_with_project_state_model(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project}, agent_name="ResearchAgent")

        res = await get_project_state(scope="summary", tool_context=ctx)
        assert res["status"] == "success"
        assert res["data"]["name"] == "Scalable GNN Literature Review"
        assert res["data"]["stages"]["stage_1_research"]["paper_count"] == 2

    @pytest.mark.asyncio
    async def test_execution_with_raw_dict_state(self) -> None:
        project = create_populated_project()
        raw_dict = project.model_dump(mode="json")
        ctx = DummyToolContext(state={"project_state": raw_dict}, agent_name="ResearchAgent")

        res = await get_project_state(scope="summary", tool_context=ctx)
        assert res["status"] == "success"
        assert res["data"]["name"] == "Scalable GNN Literature Review"

    @pytest.mark.asyncio
    async def test_execution_with_module_level_active_state(self) -> None:
        project = create_populated_project()
        set_active_project_state(project)

        # tool_context is None, should resolve from module-level state
        res = await get_project_state(scope="summary", tool_context=None)
        assert res["status"] == "success"
        assert res["data"]["name"] == "Scalable GNN Literature Review"

    @pytest.mark.asyncio
    async def test_execution_error_when_no_state_found(self) -> None:
        ctx = DummyToolContext(state={})
        res = await get_project_state(scope="summary", tool_context=ctx)
        assert res["status"] == "error"
        assert "No active project state found" in res["message"]


# ---------------------------------------------------------------------------
# 2. get_project_state Tests (Scoped Dot-Path Querying)
# ---------------------------------------------------------------------------

class TestGetProjectState:
    """Test get_project_state with summary mode, stage extraction, and dot-path navigation."""

    @pytest.mark.asyncio
    async def test_summary_mode_structure(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res = await get_project_state(scope="summary", tool_context=ctx)
        assert res["status"] == "success"
        assert res["scope"] == "summary"
        data = res["data"]
        assert data["project_id"] == project.project_id
        assert data["name"] == project.name
        assert data["topic"] == project.topic
        assert data["token_budget"] == 600000
        assert data["tokens_used"] == 12500
        assert "stages" in data
        assert data["stages"]["stage_1_research"]["status"] == "completed"
        assert data["stages"]["stage_1_research"]["paper_count"] == 2
        assert data["stages"]["stage_3_planning"]["section_count"] == 2
        assert data["message_board_total"] == 3
        assert data["unacknowledged_messages_count"] == 3

    @pytest.mark.asyncio
    async def test_stage_parameter_extraction(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Explicit stage name
        res1 = await get_project_state(stage="stage_1_research", tool_context=ctx)
        assert res1["status"] == "success"
        assert res1["stage"] == "stage_1_research"
        assert res1["data"]["meta"]["status"] == "completed"
        assert "papers" in res1["data"]["artifacts"]

        # Friendly stage name "planning"
        res2 = await get_project_state(stage="planning", tool_context=ctx)
        assert res2["status"] == "success"
        assert res2["stage"] == "stage_3_planning"
        assert len(res2["data"]["artifacts"]["outline"]["sections"]) == 2

    @pytest.mark.asyncio
    async def test_stage_parameter_with_subpath(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Query quadrant via stage and path
        res = await get_project_state(
            stage="stage_1_research",
            path="inputs.max_depth",
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["data"] == 2

    @pytest.mark.asyncio
    async def test_invalid_stage_error(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res = await get_project_state(stage="stage_invalid", tool_context=ctx)
        assert res["status"] == "error"
        assert "Invalid stage" in res["message"]

    @pytest.mark.asyncio
    async def test_dot_path_scalar_and_dict(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Scalar query
        res_scalar = await get_project_state(
            path="stage_1_research.meta.progress_percentage",
            tool_context=ctx,
        )
        assert res_scalar["status"] == "success"
        assert res_scalar["data"] == 100.0

        # Dict query
        res_dict = await get_project_state(
            path="stage_1_research.inputs.research_questions",
            tool_context=ctx,
        )
        assert res_dict["status"] == "success"
        assert len(res_dict["data"]) == 2
        assert "computational bottlenecks" in res_dict["data"][0]

    @pytest.mark.asyncio
    async def test_dot_path_compound_doi_key(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Academic DOI contains dots and slashes: 10.1145/3292500.3330964
        path = "stage_1_research.artifacts.papers.10.1145/3292500.3330964.title"
        res = await get_project_state(path=path, tool_context=ctx)
        assert res["status"] == "success"
        assert "GraphSAGE" in res["data"]

    @pytest.mark.asyncio
    async def test_dot_path_list_index(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        path = "stage_3_planning.artifacts.outline.sections.1.title"
        res = await get_project_state(path=path, tool_context=ctx)
        assert res["status"] == "success"
        assert res["data"] == "Message Passing Paradigms and Over-smoothing"

    @pytest.mark.asyncio
    async def test_invalid_dot_path_returns_error(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Nonexistent field
        res1 = await get_project_state(
            path="stage_1_research.artifacts.nonexistent_field",
            tool_context=ctx,
        )
        assert res1["status"] == "error"
        assert "failed" in res1["message"].lower()

        # List index out of range
        res2 = await get_project_state(
            path="stage_3_planning.artifacts.outline.sections.99.title",
            tool_context=ctx,
        )
        assert res2["status"] == "error"
        assert "out of range" in res2["message"].lower()

    @pytest.mark.asyncio
    async def test_scope_all(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res = await get_project_state(scope="all", tool_context=ctx)
        assert res["status"] == "success"
        assert res["scope"] == "all"
        assert "stage_1_research" in res["data"]
        assert "message_board" in res["data"]


# ---------------------------------------------------------------------------
# 3. post_to_message_board Tests
# ---------------------------------------------------------------------------

class TestPostToMessageBoard:
    """Test publishing messages across all 6 classifications, DOI normalization, and sync."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "msg_type",
        ["insight", "serendipity", "gap", "warning", "decision", "hypothesis"],
    )
    async def test_post_all_six_message_types(self, msg_type: BoardClassification) -> None:
        project = ProjectState(name="Board Post Test")
        ctx = DummyToolContext(state={"project_state": project}, agent_name="EvidenceSynthesizer")

        res = await post_to_message_board(
            message_type=msg_type,
            title=f"Sample title for {msg_type}",
            content=f"Detailed markdown content exploring {msg_type}.",
            stage="stage_2_analysis",
            tags=["evaluation", msg_type],
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["message"]["message_type"] == msg_type
        assert res["message"]["title"] == f"Sample title for {msg_type}"
        assert res["message"]["author_agent"] == "EvidenceSynthesizer"
        assert len(project.message_board) == 1
        assert project.message_board[0].message_type == msg_type

    @pytest.mark.asyncio
    async def test_post_doi_normalization(self) -> None:
        project = ProjectState(name="DOI Normalization Test")
        ctx = DummyToolContext(state={"project_state": project})

        raw_dois = [
            "https://doi.org/10.1145/3292500.3330964",
            "doi: 10.1016/j.artint.2024",
            "  HTTPS://DOI.ORG/10.1000/182_ABC  ",
        ]

        res = await post_to_message_board(
            message_type="insight",
            title="Cross-citation Insight",
            content="Normalized DOI verification.",
            related_paper_dois=raw_dois,
            tool_context=ctx,
        )
        assert res["status"] == "success"
        stored_dois = res["message"]["related_paper_dois"]
        assert stored_dois == [
            "10.1145/3292500.3330964",
            "10.1016/j.artint.2024",
            "10.1000/182_abc",
        ]

    @pytest.mark.asyncio
    async def test_post_invalid_message_type_rejected(self) -> None:
        project = ProjectState(name="Invalid Type Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await post_to_message_board(
            message_type="random_speculation",
            title="Bad Type",
            content="This should fail validation.",
            tool_context=ctx,
        )
        assert res["status"] == "error"
        assert "Invalid message_type" in res["message"]
        assert len(project.message_board) == 0

    @pytest.mark.asyncio
    async def test_post_syncs_with_raw_dict_state(self) -> None:
        project = ProjectState(name="Raw Dict Sync Test")
        raw_dict = project.model_dump(mode="json")
        ctx = DummyToolContext(state={"project_state": raw_dict}, agent_name="PlannerAgent")

        res = await post_to_message_board(
            message_type="decision",
            title="Adopted Thematic Outline",
            content="Structured by message passing, sampling, and spectral models.",
            tool_context=ctx,
        )
        assert res["status"] == "success"
        # Verify the raw dict inside tool_context.state was synchronized
        updated_dict = ctx.state["project_state"]
        assert isinstance(updated_dict, dict)
        assert len(updated_dict["message_board"]) == 1
        assert updated_dict["message_board"][0]["title"] == "Adopted Thematic Outline"


# ---------------------------------------------------------------------------
# 4. read_message_board Tests (Multi-Facet Filtering & Acknowledgments)
# ---------------------------------------------------------------------------

class TestReadMessageBoard:
    """Test read_message_board with multi-facet filtering and acknowledgment tracking."""

    @pytest.mark.asyncio
    async def test_read_filter_by_message_type(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res_serendipity = await read_message_board(
            message_type="serendipity",
            tool_context=ctx,
        )
        assert res_serendipity["status"] == "success"
        assert res_serendipity["count"] == 1
        assert res_serendipity["messages"][0]["message_type"] == "serendipity"

        res_warning = await read_message_board(
            message_type="warning",
            tool_context=ctx,
        )
        assert res_warning["status"] == "success"
        assert res_warning["count"] == 1
        assert res_warning["messages"][0]["message_type"] == "warning"

    @pytest.mark.asyncio
    async def test_read_filter_by_stage(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res = await read_message_board(
            stage="stage_2_analysis",
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["count"] == 1
        assert res["messages"][0]["stage"] == "stage_2_analysis"

    @pytest.mark.asyncio
    async def test_read_filter_by_tag(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Match "hardware"
        res = await read_message_board(tag="hardware", tool_context=ctx)
        assert res["status"] == "success"
        assert res["count"] == 1
        assert "hardware" in res["messages"][0]["tags"]

    @pytest.mark.asyncio
    async def test_read_filter_by_doi(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Query using unnormalized DOI URL
        query_doi = "https://doi.org/10.1145/3292500.3330964"
        res = await read_message_board(paper_doi=query_doi, tool_context=ctx)
        assert res["status"] == "success"
        # Should match the warning message referencing doi_1 and doi_2
        assert res["count"] == 1
        assert res["messages"][0]["message_type"] == "warning"

    @pytest.mark.asyncio
    async def test_read_unacknowledged_only_and_marking(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project}, agent_name="PlannerAgent")

        # Initially all 3 are unacknowledged by PlannerAgent
        res_all = await read_message_board(unacknowledged_only=True, tool_context=ctx)
        assert res_all["count"] == 3

        # Read warnings and mark as acknowledged
        res_warn = await read_message_board(
            message_type="warning",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res_warn["count"] == 1

        # Now query unacknowledged_only again
        res_remaining = await read_message_board(
            unacknowledged_only=True,
            tool_context=ctx,
        )
        assert res_remaining["count"] == 2
        # The warning should no longer appear in unacknowledged
        types_remaining = [m["message_type"] for m in res_remaining["messages"]]
        assert "warning" not in types_remaining

    @pytest.mark.asyncio
    async def test_read_limit(self) -> None:
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        res = await read_message_board(limit=1, tool_context=ctx)
        assert res["status"] == "success"
        assert res["count"] == 1


# ---------------------------------------------------------------------------
# 5. update_stage_substate Tests (Scoped Mutation, Deep Merge & Validation)
# ---------------------------------------------------------------------------

class TestUpdateStageSubstate:
    """Test scoped quadrant mutation with deep-merge preservation and validation."""

    @pytest.mark.asyncio
    async def test_update_meta_quadrant(self) -> None:
        project = ProjectState(name="Meta Mutation Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="meta",
            data={"status": "in_progress", "progress_percentage": 50.0, "agent_name": "ALRSAgent"},
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["stage"] == "stage_1_research"
        assert res["quadrant"] == "meta"
        assert project.stage_1_research.meta.status == "in_progress"
        assert project.stage_1_research.meta.progress_percentage == 50.0
        assert project.stage_1_research.meta.agent_name == "ALRSAgent"

    @pytest.mark.asyncio
    async def test_update_inputs_quadrant(self) -> None:
        project = ProjectState(name="Inputs Mutation Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="inputs",
            data={"max_depth": 3, "similarity_threshold": 0.75},
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert project.stage_1_research.inputs.max_depth == 3
        assert project.stage_1_research.inputs.similarity_threshold == 0.75
        # Existing default values must be preserved
        assert project.stage_1_research.inputs.max_papers == 50

    @pytest.mark.asyncio
    async def test_artifacts_deep_merge_preserves_existing_papers(self) -> None:
        """CRITICAL: Adding new papers must NOT overwrite existing papers in the library."""
        project = create_populated_project()
        ctx = DummyToolContext(state={"project_state": project})

        # Confirm initial state has 2 papers
        initial_dois = list(project.stage_1_research.artifacts.papers.keys())
        assert len(initial_dois) == 2
        assert "10.1145/3292500.3330964" in initial_dois

        # Add a 3rd paper via update_stage_substate
        doi_3 = "10.1109/icml.2024.12345"
        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="artifacts",
            data={
                "papers": {
                    doi_3: {
                        "doi": doi_3,
                        "title": "Sub-graph Sampling for Scalable GNNs",
                        "authors": ["Carol Danvers"],
                        "year": 2024,
                        "citation_count": 5,
                    }
                }
            },
            tool_context=ctx,
        )
        assert res["status"] == "success"

        # Verify all 3 papers exist! (Existing papers were NOT wiped out)
        papers = project.stage_1_research.artifacts.papers
        assert len(papers) == 3
        assert "10.1145/3292500.3330964" in papers
        assert "10.1016/j.artint.2024.103342" in papers
        assert doi_3 in papers
        assert papers[doi_3].title == "Sub-graph Sampling for Scalable GNNs"

        # Verify field update on an existing paper preserves its other fields
        res_update = await update_stage_substate(
            stage="stage_1_research",
            quadrant="artifacts",
            data={
                "papers": {
                    doi_3: {
                        "citation_count": 50,
                    }
                }
            },
            tool_context=ctx,
        )
        assert res_update["status"] == "success"
        assert project.stage_1_research.artifacts.papers[doi_3].citation_count == 50
        assert project.stage_1_research.artifacts.papers[doi_3].title == "Sub-graph Sampling for Scalable GNNs"

    @pytest.mark.asyncio
    async def test_update_notes_quadrant(self) -> None:
        project = ProjectState(name="Notes Mutation Test")
        ctx = DummyToolContext(state={"project_state": project}, agent_name="ReviewerAgent")

        res = await update_stage_substate(
            stage="stage_4_writing",
            quadrant="notes",
            data=[
                {"content": "Section 2 needs deeper analysis of spectral vs spatial GNNs."},
                StageNote(author="PlannerAgent", content="Consider table comparing hardware FLOPs."),
            ],
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert len(project.stage_4_writing.notes) == 2
        assert project.stage_4_writing.notes[0].author == "ReviewerAgent"
        assert "spectral vs spatial" in project.stage_4_writing.notes[0].content
        assert project.stage_4_writing.notes[1].author == "PlannerAgent"

    @pytest.mark.asyncio
    async def test_validation_enforcement_during_mutation(self) -> None:
        """Invalid inputs must be rejected during mutation with error status."""
        project = ProjectState(name="Validation Test")
        ctx = DummyToolContext(state={"project_state": project})

        # similarity_threshold must be <= 1.0 (Field(ge=0.0, le=1.0))
        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="inputs",
            data={"similarity_threshold": 5.0},
            tool_context=ctx,
        )
        assert res["status"] == "error"
        assert "Validation failed" in res["message"]
        # State was not mutated
        assert project.stage_1_research.inputs.similarity_threshold == 0.6

    @pytest.mark.asyncio
    async def test_invalid_stage_rejection(self) -> None:
        project = ProjectState(name="Bad Stage Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await update_stage_substate(
            stage="stage_unknown",
            quadrant="meta",
            data={"status": "in_progress"},
            tool_context=ctx,
        )
        assert res["status"] == "error"
        assert "Invalid stage" in res["message"]

    @pytest.mark.asyncio
    async def test_invalid_quadrant_rejection(self) -> None:
        project = ProjectState(name="Bad Quadrant Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="invalid_quadrant",
            data={"foo": "bar"},
            tool_context=ctx,
        )
        assert res["status"] == "error"
        assert "Invalid quadrant" in res["message"]

    @pytest.mark.asyncio
    async def test_mutation_syncs_with_raw_dict_state(self) -> None:
        project = ProjectState(name="Raw Dict Mutation Test")
        raw_dict = project.model_dump(mode="json")
        ctx = DummyToolContext(state={"project_state": raw_dict})

        res = await update_stage_substate(
            stage="stage_1_research",
            quadrant="inputs",
            data={"max_depth": 4},
            tool_context=ctx,
        )
        assert res["status"] == "success"
        # Assert raw dict in context was updated
        updated_dict = ctx.state["project_state"]
        assert updated_dict["stage_1_research"]["inputs"]["max_depth"] == 4


class TestStageLifecycleTools:
    """Tests for transition_to_stage and get_stage_status lifecycle tools."""

    @pytest.mark.asyncio
    async def test_transition_to_stage_sequential_progression(self) -> None:
        project = ProjectState(name="Lifecycle Test")
        ctx = DummyToolContext(state={"project_state": project}, agent_name="ResearchAgent")

        # Check initial status
        status_res = await get_stage_status(tool_context=ctx)
        assert status_res["status"] == "success"
        assert status_res["current_stage"] == "stage_1_research"
        assert status_res["stage_status"] == "not_started"

        # Transition to stage 2
        res = await transition_to_stage(
            target_stage="stage_2_analysis",
            summary="Stage 1 research questions and initial papers collected.",
            tool_context=ctx,
        )
        assert res["status"] == "success"
        assert res["previous_stage"] == "stage_1_research"
        assert res["current_stage"] == "stage_2_analysis"

        # Verify stage 1 is marked completed and stage 2 is in_progress
        assert project.stage_1_research.meta.status == "completed"
        assert project.stage_1_research.meta.progress_percentage == 100.0
        assert project.stage_2_analysis.meta.status == "in_progress"
        assert project.current_stage == "stage_2_analysis"

        # Verify decision was logged on message board
        board_posts = [m for m in project.message_board if m.message_type == "decision"]
        assert len(board_posts) >= 1
        assert "Stage Transition" in board_posts[0].title

        # Verify read_message_board tool returns the transition decision
        board_res = await read_message_board(message_type="decision", tool_context=ctx)
        assert board_res["status"] == "success"
        assert len(board_res["messages"]) >= 1

        # Verify get_stage_status reports new stage
        status_res2 = await get_stage_status(tool_context=ctx)
        assert status_res2["status"] == "success"
        assert status_res2["current_stage"] == "stage_2_analysis"
        assert status_res2["stage_status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_transition_to_stage_invalid_stage(self) -> None:
        project = ProjectState(name="Invalid Stage Test")
        ctx = DummyToolContext(state={"project_state": project})

        res = await transition_to_stage(
            target_stage="non_existent_stage",
            tool_context=ctx,
        )
        assert res["status"] == "error"
        assert "Unknown stage" in res["message"]

    @pytest.mark.asyncio
    async def test_transition_to_stage_no_state(self) -> None:
        ctx = DummyToolContext(state={})
        res = await transition_to_stage(target_stage="stage_2_analysis", tool_context=ctx)
        assert res["status"] == "error"
        assert "No active project state found" in res["message"]

