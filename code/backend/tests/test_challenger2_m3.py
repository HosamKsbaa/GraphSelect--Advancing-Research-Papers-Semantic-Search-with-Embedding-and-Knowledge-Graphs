"""Empirical Adversarial Test Suite by Challenger 2 for Milestone 3 (Requirement R4).

Focus Areas:
1. tool_context state handling:
   - Dict vs Pydantic model in tool_context.state["project_state"]
   - Preservation of dict type and synchronized updates across multiple mutations
   - Corrupt/invalid dict handling
   - tool_context as dict, as ProjectState, or with custom mapping state
2. read_message_board filtering:
   - Combined multi-facet filters: message_type, stage, tag, DOI, and unacknowledged_only
   - Multiple tags, case-insensitivity, partial matching
   - Handling of tags passed in kwargs
3. Acknowledgment tracking:
   - mark_as_acknowledged=True semantics and idempotency
   - Scoped acknowledgment (only filtered messages marked)
   - Interaction with unacknowledged_only
   - Interaction with limit (unreturned messages marked vs returned messages)
   - State synchronization back to raw dict vs Pydantic model
"""
from __future__ import annotations

import copy
import pytest
from typing import Any

from features.workflow.state_models import (
    BoardClassification,
    BoardMessage,
    PaperMetadata,
    ProjectState,
    ResearchArtifacts,
    ResearchGap,
    ResearchInputs,
    SectionBlueprint,
    StageMeta,
    StageNote,
    normalize_doi,
)
from features.workflow.state_tools import (
    deep_merge,
    get_project_state,
    post_to_message_board,
    read_message_board,
    set_active_project_state,
    update_stage_substate,
)


# ---------------------------------------------------------------------------
# Test Doubles
# ---------------------------------------------------------------------------

class MockAgent:
    """Mock ADK agent."""
    def __init__(self, name: str = "ResearchAgent") -> None:
        self.name = name


class MockToolContext:
    """Mock ADK ToolContext container."""
    def __init__(
        self,
        state: dict[str, Any] | None = None,
        agent_name: str = "ResearchAgent",
    ) -> None:
        self.state: dict[str, Any] = state if state is not None else {}
        self.agent = MockAgent(agent_name)


class CustomMappingState:
    """Mock session state object that behaves like a dictionary/mapping."""
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = initial if initial is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data


class CustomContextWithMapping:
    """Mock ToolContext whose .state is a CustomMappingState instead of a dict."""
    def __init__(self, initial_state: dict[str, Any], agent_name: str = "WriterAgent") -> None:
        self.state = CustomMappingState(initial_state)
        self.agent = MockAgent(agent_name)


@pytest.fixture(autouse=True)
def reset_active_state() -> None:
    """Reset module-level active project state before and after each test."""
    set_active_project_state(None)
    yield
    set_active_project_state(None)


def build_test_project() -> ProjectState:
    """Construct a populated ProjectState with seed papers, outlines, and board messages."""
    project = ProjectState(
        name="Empirical Graph Representation Survey",
        topic="Message Passing Over-smoothing and Spectral GNNs",
        token_budget=800000,
        tokens_used=45000,
    )

    doi_1 = "10.1145/3292500.3330964"
    doi_2 = "10.1016/j.artint.2024.103342"
    doi_3 = "10.1109/icml.2023.9999"

    # Stage 1: Research
    project.stage_1_research.meta.status = "completed"
    project.stage_1_research.meta.progress_percentage = 100.0
    project.stage_1_research.meta.agent_name = "ResearchAgent"
    project.stage_1_research.inputs.research_questions = [
        "What causes catastrophic over-smoothing in deep GCNs?",
        "Do residual connections preserve high-frequency graph signals?",
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

    # Stage 2: Analysis
    project.stage_2_analysis.meta.status = "in_progress"
    project.stage_2_analysis.meta.agent_name = "GapFinderAgent"
    project.stage_2_analysis.meta.progress_percentage = 60.0
    project.stage_2_analysis.artifacts.research_gaps = [
        ResearchGap(
            question="What is the latency on edge NPUs?",
            description="Lack of benchmark datasets with diameter > 20",
        ),
        ResearchGap(
            question="Are high-diameter graphs evaluated?",
            description="Sparse empirical evaluations on edge NPUs",
        ),
    ]

    # Stage 3: Planning
    project.stage_3_planning.meta.status = "not_started"
    project.stage_3_planning.artifacts.outline.sections = [
        SectionBlueprint(
            title="Foundations of Graph Representation Learning",
            order=1,
            level=1,
            target_word_count=1500,
            assigned_dois=[doi_1],
        ),
        SectionBlueprint(
            title="Analysis of Over-smoothing and Spectral Solutions",
            order=2,
            level=1,
            target_word_count=2500,
            assigned_dois=[doi_1, doi_2],
        ),
    ]

    # Message Board entries across types, stages, tags, DOIs
    # Msg 1: Serendipity from Stage 1
    project.post_message(
        author_agent="ResearchAgent",
        message_type="serendipity",
        title="Unexpected connection to heat diffusion PDE",
        content="Graph heat kernel directly diagonalizes the graph Laplacian.",
        stage="stage_1_research",
        tags=["diffusion", "physics", "spectral"],
        related_paper_dois=[doi_1],
    )
    # Msg 2: Gap from Stage 2
    project.post_message(
        author_agent="GapFinderAgent",
        message_type="gap",
        title="Edge NPU Latency Gap",
        content="Zero published papers measure milliwatt energy consumption on ARM NPUs.",
        stage="stage_2_analysis",
        tags=["hardware", "edge", "benchmarking"],
        related_paper_dois=[doi_2],
    )
    # Msg 3: Warning from Stage 2
    project.post_message(
        author_agent="GapFinderAgent",
        message_type="warning",
        title="Contradictory time complexity bounds",
        content="Paper A claims O(V+E) while Paper B proves O(V*E) on power-law graphs.",
        stage="stage_2_analysis",
        tags=["complexity", "bounds", "graph"],
        related_paper_dois=[doi_1, doi_2],
    )
    # Msg 4: Decision from Stage 3
    project.post_message(
        author_agent="PlannerAgent",
        message_type="decision",
        title="Adopt 4-part comparative structure",
        content="Structure review by theoretical foundations, sampling paradigms, scaling, and open gaps.",
        stage="stage_3_planning",
        tags=["structure", "planning"],
    )
    # Msg 5: Hypothesis from Stage 1
    project.post_message(
        author_agent="ResearchAgent",
        message_type="hypothesis",
        title="Dirichlet energy decay rate predicts over-smoothing",
        content="Hypothesize Dirichlet energy drops exponentially with layer depth L.",
        stage="stage_1_research",
        tags=["dirichlet", "physics", "oversmoothing"],
        related_paper_dois=[doi_1, doi_3],
    )

    return project


# ===========================================================================
# 1. Adversarial Tests: tool_context State Handling (Dict vs Pydantic Model)
# ===========================================================================

class TestToolContextStateHandling:
    """Adversarially challenges state handling across Pydantic models, raw dicts, and mutations."""

    @pytest.mark.asyncio
    async def test_pydantic_model_full_lifecycle(self) -> None:
        """Pydantic model in tool_context.state: reads, mutations, board posts, and sync."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="ResearchAgent")

        # 1. Verify read
        res_summary = await get_project_state(scope="summary", tool_context=ctx)
        assert res_summary["status"] == "success"
        assert res_summary["data"]["name"] == "Empirical Graph Representation Survey"
        assert res_summary["data"]["tokens_used"] == 45000

        # 2. Mutate meta quadrant
        res_meta = await update_stage_substate(
            stage="stage_2_analysis",
            quadrant="meta",
            data={"progress_percentage": 85.0, "status": "completed"},
            tool_context=ctx,
        )
        assert res_meta["status"] == "success"
        # Verify in-place mutation on Pydantic instance in context
        assert ctx.state["project_state"].stage_2_analysis.meta.progress_percentage == 85.0
        assert ctx.state["project_state"].stage_2_analysis.meta.status == "completed"

        # 3. Mutate artifacts quadrant (add new paper)
        new_doi = "10.1145/new.gnn.2024"
        res_art = await update_stage_substate(
            stage="stage_1_research",
            quadrant="artifacts",
            data={
                "papers": {
                    new_doi: {
                        "doi": new_doi,
                        "title": "Scalable Graph Embeddings with Fast Sampling",
                        "authors": ["Alice Smith"],
                        "year": 2024,
                    }
                }
            },
            tool_context=ctx,
        )
        assert res_art["status"] == "success"
        # Verify paper was added and existing papers preserved on the model
        papers = ctx.state["project_state"].stage_1_research.artifacts.papers
        assert len(papers) == 3
        assert new_doi in papers
        assert "10.1145/3292500.3330964" in papers

        # 4. Post to message board
        res_post = await post_to_message_board(
            message_type="insight",
            title="Fast Sampling Achieves O(1) Per-node Complexity",
            content="Layer-dependent sampling decouples node degrees.",
            stage="stage_1_research",
            tags=["sampling", "complexity"],
            related_paper_dois=[new_doi],
            tool_context=ctx,
        )
        assert res_post["status"] == "success"
        assert len(ctx.state["project_state"].message_board) == 6
        assert ctx.state["project_state"].message_board[-1].title == "Fast Sampling Achieves O(1) Per-node Complexity"

        # 5. Read dot-path of newly mutated paper
        res_dot = await get_project_state(
            path=f"stage_1_research.artifacts.papers.{new_doi}.title",
            tool_context=ctx,
        )
        assert res_dot["status"] == "success"
        assert res_dot["data"] == "Scalable Graph Embeddings with Fast Sampling"

    @pytest.mark.asyncio
    async def test_raw_dict_full_lifecycle_and_dict_preservation(self) -> None:
        """Raw dict in tool_context.state: mutations must update the dict and preserve dict type."""
        project = build_test_project()
        raw_dict = project.model_dump(mode="json")
        ctx = MockToolContext(state={"project_state": raw_dict}, agent_name="ResearchAgent")

        assert isinstance(ctx.state["project_state"], dict)

        # 1. Read summary from raw dict
        res_summary = await get_project_state(scope="summary", tool_context=ctx)
        assert res_summary["status"] == "success"
        assert res_summary["data"]["name"] == "Empirical Graph Representation Survey"
        assert res_summary["data"]["stages"]["stage_1_research"]["paper_count"] == 2

        # 2. Mutate meta quadrant on raw dict
        res_meta = await update_stage_substate(
            stage="stage_2_analysis",
            quadrant="meta",
            data={"progress_percentage": 90.0, "status": "completed"},
            tool_context=ctx,
        )
        assert res_meta["status"] == "success"
        # CRITICAL ASSERTION: ctx.state["project_state"] must REMAIN a dict, NOT become a Pydantic model
        assert isinstance(ctx.state["project_state"], dict)
        assert ctx.state["project_state"]["stage_2_analysis"]["meta"]["progress_percentage"] == 90.0
        assert ctx.state["project_state"]["stage_2_analysis"]["meta"]["status"] == "completed"

        # 3. Mutate artifacts quadrant on raw dict (add a paper)
        new_doi = "10.1109/dict.paper.2024"
        res_art = await update_stage_substate(
            stage="stage_1_research",
            quadrant="artifacts",
            data={
                "papers": {
                    new_doi: {
                        "doi": new_doi,
                        "title": "Dict Representation Test Paper",
                        "authors": ["Bob Builder"],
                        "year": 2024,
                    }
                }
            },
            tool_context=ctx,
        )
        assert res_art["status"] == "success"
        assert isinstance(ctx.state["project_state"], dict)
        stored_papers = ctx.state["project_state"]["stage_1_research"]["artifacts"]["papers"]
        assert len(stored_papers) == 3
        assert new_doi in stored_papers
        assert "10.1145/3292500.3330964" in stored_papers

        # 4. Post to message board on raw dict
        res_post = await post_to_message_board(
            message_type="gap",
            title="Dict Mode Gap Discovered",
            content="Testing message board posting when state is a raw dict.",
            stage="stage_2_analysis",
            tags=["raw_dict", "gap"],
            tool_context=ctx,
        )
        assert res_post["status"] == "success"
        assert isinstance(ctx.state["project_state"], dict)
        board = ctx.state["project_state"]["message_board"]
        assert len(board) == 6
        assert board[-1]["title"] == "Dict Mode Gap Discovered"

        # 5. Read dot-path into newly created paper from raw dict
        res_dot = await get_project_state(
            path=f"stage_1_research.artifacts.papers.{new_doi}.title",
            tool_context=ctx,
        )
        assert res_dot["status"] == "success"
        assert res_dot["data"] == "Dict Representation Test Paper"

    @pytest.mark.asyncio
    async def test_sequential_mutations_accumulate_on_raw_dict(self) -> None:
        """Multiple sequential mutations across different quadrants and stages on raw dict."""
        project = build_test_project()
        raw_dict = project.model_dump(mode="json")
        ctx = MockToolContext(state={"project_state": raw_dict}, agent_name="WriterAgent")

        # Mutation 1: Stage 1 inputs
        await update_stage_substate(
            stage="stage_1_research",
            quadrant="inputs",
            data={"max_depth": 4},
            tool_context=ctx,
        )
        # Mutation 2: Stage 3 meta
        await update_stage_substate(
            stage="stage_3_planning",
            quadrant="meta",
            data={"status": "in_progress", "progress_percentage": 25.0},
            tool_context=ctx,
        )
        # Mutation 3: Stage 4 inputs
        await update_stage_substate(
            stage="stage_4_writing",
            quadrant="inputs",
            data={"target_level": "phd", "tone": "formal_academic"},
            tool_context=ctx,
        )

        state_dict = ctx.state["project_state"]
        assert isinstance(state_dict, dict)
        # All three mutations must be present!
        assert state_dict["stage_1_research"]["inputs"]["max_depth"] == 4
        assert state_dict["stage_3_planning"]["meta"]["status"] == "in_progress"
        assert state_dict["stage_3_planning"]["meta"]["progress_percentage"] == 25.0
        assert state_dict["stage_4_writing"]["inputs"]["target_level"] == "phd"
        assert state_dict["stage_4_writing"]["inputs"]["tone"] == "formal_academic"

    @pytest.mark.asyncio
    async def test_corrupt_or_invalid_dict_state_handled_gracefully(self) -> None:
        """If tool_context.state['project_state'] contains corrupt data, tools must return error gracefully."""
        # Case A: Missing required 'name' and invalid types
        corrupt_state = {"invalid_key": 12345, "status": "nonexistent_status"}
        ctx = MockToolContext(state={"project_state": corrupt_state})

        res_get = await get_project_state(scope="summary", tool_context=ctx)
        assert res_get["status"] == "error"
        assert "No active project state found" in res_get["message"]

        res_post = await post_to_message_board(
            message_type="insight",
            title="Test",
            content="Content",
            tool_context=ctx,
        )
        assert res_post["status"] == "error"
        assert "No active project state found" in res_post["message"]

        res_read = await read_message_board(tool_context=ctx)
        assert res_read["status"] == "error"
        assert "No active project state found" in res_read["message"]

        res_mut = await update_stage_substate(
            stage="stage_1_research",
            quadrant="meta",
            data={"status": "in_progress"},
            tool_context=ctx,
        )
        assert res_mut["status"] == "error"
        assert "No active project state found" in res_mut["message"]

    @pytest.mark.asyncio
    async def test_tool_context_is_dict_itself(self) -> None:
        """When tool_context is a dict itself (e.g. {'project_state': dict, 'agent_name': 'X'})."""
        project = build_test_project()
        raw_dict = project.model_dump(mode="json")
        ctx_dict = {"project_state": raw_dict, "agent_name": "EvidenceSynthesizer"}

        res_get = await get_project_state(scope="summary", tool_context=ctx_dict)
        assert res_get["status"] == "success"
        assert res_get["data"]["name"] == "Empirical Graph Representation Survey"

        res_mut = await update_stage_substate(
            stage="stage_1_research",
            quadrant="meta",
            data={"progress_percentage": 99.0},
            tool_context=ctx_dict,
        )
        assert res_mut["status"] == "success"
        assert ctx_dict["project_state"]["stage_1_research"]["meta"]["progress_percentage"] == 99.0

    @pytest.mark.asyncio
    async def test_tool_context_with_custom_mapping_state(self) -> None:
        """ToolContext whose .state is a custom mapping class (like ADK session states)."""
        project = build_test_project()
        raw_dict = project.model_dump(mode="json")
        ctx = CustomContextWithMapping(
            initial_state={"project_state": raw_dict},
            agent_name="CustomAgent",
        )

        res_get = await get_project_state(scope="summary", tool_context=ctx)
        assert res_get["status"] == "success"

        res_mut = await update_stage_substate(
            stage="stage_1_research",
            quadrant="inputs",
            data={"max_depth": 5},
            tool_context=ctx,
        )
        assert res_mut["status"] == "success"
        assert ctx.state["project_state"]["stage_1_research"]["inputs"]["max_depth"] == 5

    @pytest.mark.asyncio
    async def test_tool_context_is_project_state_directly(self) -> None:
        """When tool_context passed to the tool is a ProjectState instance directly."""
        project = build_test_project()

        res_get = await get_project_state(scope="summary", tool_context=project)
        assert res_get["status"] == "success"
        assert res_get["data"]["name"] == "Empirical Graph Representation Survey"

        res_post = await post_to_message_board(
            message_type="insight",
            title="Direct ProjectState Context",
            content="Posting directly into ProjectState as tool_context.",
            tool_context=project,
        )
        assert res_post["status"] == "success"
        assert len(project.message_board) == 6


# ===========================================================================
# 2. Adversarial Tests: read_message_board Multi-Facet Filtering
# ===========================================================================

class TestReadMessageBoardFiltering:
    """Adversarially challenges multi-facet filtering across types, stages, tags, DOIs, and unacknowledged status."""

    @pytest.mark.asyncio
    async def test_filter_combined_type_stage_tag(self) -> None:
        """Multi-facet filter: message_type + stage + tag must perform strict intersection."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        # Query 1: type=serendipity, stage=stage_1_research, tag=diffusion
        res1 = await read_message_board(
            message_type="serendipity",
            stage="stage_1_research",
            tag="diffusion",
            tool_context=ctx,
        )
        assert res1["status"] == "success"
        assert res1["count"] == 1
        assert res1["messages"][0]["title"] == "Unexpected connection to heat diffusion PDE"

        # Query 2: same stage and tag, but non-matching message_type
        res2 = await read_message_board(
            message_type="warning",
            stage="stage_1_research",
            tag="diffusion",
            tool_context=ctx,
        )
        assert res2["status"] == "success"
        assert res2["count"] == 0

        # Query 3: same type and tag, but non-matching stage
        res3 = await read_message_board(
            message_type="serendipity",
            stage="stage_3_planning",
            tag="diffusion",
            tool_context=ctx,
        )
        assert res3["status"] == "success"
        assert res3["count"] == 0

    @pytest.mark.asyncio
    async def test_filter_combined_type_and_doi(self) -> None:
        """Multi-facet filter: message_type + DOI URL resolver normalization."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        doi_1 = "10.1145/3292500.3330964"
        doi_2 = "10.1016/j.artint.2024.103342"

        # Query: warning with doi_1 (passed with URL prefix)
        res_warn_doi1 = await read_message_board(
            message_type="warning",
            paper_doi=f"https://doi.org/{doi_1}",
            tool_context=ctx,
        )
        assert res_warn_doi1["status"] == "success"
        assert res_warn_doi1["count"] == 1
        assert res_warn_doi1["messages"][0]["title"] == "Contradictory time complexity bounds"

        # Query: gap with doi_1 -> Msg 2 is gap but with doi_2, not doi_1 -> should return 0
        res_gap_doi1 = await read_message_board(
            message_type="gap",
            paper_doi=doi_1,
            tool_context=ctx,
        )
        assert res_gap_doi1["status"] == "success"
        assert res_gap_doi1["count"] == 0

        # Query: gap with doi_2 -> should return Msg 2
        res_gap_doi2 = await read_message_board(
            message_type="gap",
            paper_doi=f"doi: {doi_2}",
            tool_context=ctx,
        )
        assert res_gap_doi2["status"] == "success"
        assert res_gap_doi2["count"] == 1
        assert res_gap_doi2["messages"][0]["title"] == "Edge NPU Latency Gap"

    @pytest.mark.asyncio
    async def test_filter_combined_type_tag_and_unacknowledged(self) -> None:
        """Multi-facet filter: message_type + tag + unacknowledged_only for a specific agent."""
        project = build_test_project()
        ctx_researcher = MockToolContext(state={"project_state": project}, agent_name="ResearchAgent")
        ctx_planner = MockToolContext(state={"project_state": project}, agent_name="PlannerAgent")

        # Initially, all 5 messages are unacknowledged
        res_init = await read_message_board(unacknowledged_only=True, tool_context=ctx_researcher)
        assert res_init["count"] == 5

        # Acknowledge Msg 1 ("diffusion") by ResearchAgent
        msg1_id = project.message_board[0].id
        project.acknowledge_message(msg1_id, "ResearchAgent")

        # Now ResearchAgent queries with tag="diffusion" and unacknowledged_only=True
        # Msg 1 has tag="diffusion", but was acknowledged by ResearchAgent -> MUST NOT be returned!
        res_researcher_diff = await read_message_board(
            tag="diffusion",
            unacknowledged_only=True,
            tool_context=ctx_researcher,
        )
        assert res_researcher_diff["count"] == 0

        # BUT PlannerAgent has NOT acknowledged Msg 1 -> PlannerAgent MUST see it!
        res_planner_diff = await read_message_board(
            tag="diffusion",
            unacknowledged_only=True,
            tool_context=ctx_planner,
        )
        assert res_planner_diff["count"] == 1
        assert res_planner_diff["messages"][0]["id"] == msg1_id

    @pytest.mark.asyncio
    async def test_tag_filtering_case_insensitivity_and_partial_matching(self) -> None:
        """Tag filtering must be case-insensitive and support substring matching."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        # Msg 2 has tags: ["hardware", "edge", "benchmarking"]
        # Exact lowercase
        res1 = await read_message_board(tag="hardware", tool_context=ctx)
        assert res1["count"] == 1

        # Uppercase
        res2 = await read_message_board(tag="HARDWARE", tool_context=ctx)
        assert res2["count"] == 1

        # Mixed case
        res3 = await read_message_board(tag="Edge", tool_context=ctx)
        assert res3["count"] == 1

        # Substring: "bench" matches "benchmarking"
        res4 = await read_message_board(tag="bench", tool_context=ctx)
        assert res4["count"] == 1

        # Non-matching tag
        res5 = await read_message_board(tag="quantum", tool_context=ctx)
        assert res5["count"] == 0

    @pytest.mark.asyncio
    async def test_tag_list_in_kwargs_first_item_fallback(self) -> None:
        """Empirically document and verify kwargs.get('tags') behavior."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        # Passing tags as a list via kwargs
        res = await read_message_board(tags=["physics", "nonexistent"], tool_context=ctx)
        assert res["status"] == "success"
        # The implementation picks kwargs.get('tags')[0] ("physics")
        # Msg 1 and Msg 5 have tag "physics"
        assert res["count"] == 2
        titles = [m["title"] for m in res["messages"]]
        assert "Unexpected connection to heat diffusion PDE" in titles
        assert "Dirichlet energy decay rate predicts over-smoothing" in titles

    @pytest.mark.asyncio
    async def test_unacknowledged_by_explicit_agent_kwarg(self) -> None:
        """Test unacknowledged_by kwarg filtering for a third-party agent."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="SystemAgent")

        # Acknowledge Msg 1 by ALRSAgent
        project.message_board[0].acknowledge("ALRSAgent")

        # Query unacknowledged_by="ALRSAgent"
        res = await read_message_board(
            unacknowledged_only=True,
            unacknowledged_by="ALRSAgent",
            tool_context=ctx,
        )
        # Out of 5 messages, 1 was acknowledged by ALRSAgent, so 4 remaining
        assert res["count"] == 4
        assert project.message_board[0].id not in [m["id"] for m in res["messages"]]


# ===========================================================================
# 3. Adversarial Tests: Acknowledgment Marking (mark_as_acknowledged=True)
# ===========================================================================

class TestAcknowledgmentMarking:
    """Adversarially challenges acknowledgment marking, idempotency, scoping, and state sync."""

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_basic_and_idempotent(self) -> None:
        """mark_as_acknowledged=True marks message for detected agent and is idempotent."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="ReviewerAgent")

        # Read warnings with mark_as_acknowledged=True
        res1 = await read_message_board(
            message_type="warning",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res1["status"] == "success"
        assert res1["count"] == 1

        # Check in project state
        warn_msg = [m for m in project.message_board if m.message_type == "warning"][0]
        assert "ReviewerAgent" in warn_msg.acknowledged_by
        assert len(warn_msg.acknowledged_by) == 1

        # Call again: must be idempotent, not duplicate "ReviewerAgent"
        res2 = await read_message_board(
            message_type="warning",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res2["status"] == "success"
        assert warn_msg.acknowledged_by == ["ReviewerAgent"]

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_only_affects_filtered_messages(self) -> None:
        """CRITICAL: mark_as_acknowledged must ONLY mark the filtered messages, NOT the whole board!"""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="PlanningAgent")

        # Filter by message_type="gap" and mark as acknowledged
        res = await read_message_board(
            message_type="gap",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res["count"] == 1
        gap_msg_id = res["messages"][0]["id"]

        # Verify ONLY the gap message was marked
        for m in project.message_board:
            if m.id == gap_msg_id:
                assert "PlanningAgent" in m.acknowledged_by
            else:
                assert "PlanningAgent" not in m.acknowledged_by, (
                    f"Message {m.id} ({m.message_type}) was unintentionally marked acknowledged!"
                )

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_with_unacknowledged_only_workflow(self) -> None:
        """Calling with unacknowledged_only=True and mark_as_acknowledged=True empties inbox."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="WorkflowRunner")

        # Initial: 5 unacknowledged
        res_first = await read_message_board(
            unacknowledged_only=True,
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res_first["count"] == 5

        # Immediate second call: inbox should be 0!
        res_second = await read_message_board(
            unacknowledged_only=True,
            tool_context=ctx,
        )
        assert res_second["count"] == 0

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_syncs_to_raw_dict(self) -> None:
        """When state is a raw dict, mark_as_acknowledged=True must persist to the dict."""
        project = build_test_project()
        raw_dict = project.model_dump(mode="json")
        ctx = MockToolContext(state={"project_state": raw_dict}, agent_name="AsyncWorker")

        # Verify initial dict has no acknowledgments
        for m in ctx.state["project_state"]["message_board"]:
            assert "AsyncWorker" not in m["acknowledged_by"]

        # Acknowledge warnings
        res = await read_message_board(
            message_type="warning",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res["status"] == "success"

        # Verify raw dict in tool_context.state was updated
        updated_dict = ctx.state["project_state"]
        assert isinstance(updated_dict, dict)
        warn_entry = [m for m in updated_dict["message_board"] if m["message_type"] == "warning"][0]
        assert "AsyncWorker" in warn_entry["acknowledged_by"]

        # Other entries in the dict must NOT have AsyncWorker
        other_entries = [m for m in updated_dict["message_board"] if m["message_type"] != "warning"]
        for m in other_entries:
            assert "AsyncWorker" not in m["acknowledged_by"]

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_with_limit_adversarial_investigation(self) -> None:
        """ADVERSARIAL PROBE: Does limit=N mark all filtered messages or only the N returned messages?

        When an agent asks for limit=1 with mark_as_acknowledged=True:
        If all 5 matching messages are marked acknowledged, the agent loses the 4 unreturned messages
        from its unacknowledged queue without ever seeing them.
        """
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="BatchAgent")

        # 5 unacknowledged messages exist.
        # BatchAgent asks for limit=2 with mark_as_acknowledged=True
        res = await read_message_board(
            unacknowledged_only=True,
            limit=2,
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res["count"] == 2
        returned_ids = {m["id"] for m in res["messages"]}

        # Check how many messages on the board were marked as acknowledged by BatchAgent
        marked_messages = [m for m in project.message_board if "BatchAgent" in m.acknowledged_by]
        marked_ids = {m.id for m in marked_messages}

        # VERIFICATION OF FIX:
        # In state_tools.py:
        # `results = filtered[-limit:]` is sliced BEFORE the acknowledgment loop.
        # Therefore, only the 2 returned messages are marked as acknowledged!
        assert len(marked_ids) == 2, f"Expected 2 marked messages due to post-slice loop, got {len(marked_ids)}"
        assert marked_ids == returned_ids

        # Next call by BatchAgent with unacknowledged_only=True returns the remaining 3!
        # The unreturned messages remain unacknowledged in the agent's queue.
        res_next = await read_message_board(unacknowledged_only=True, tool_context=ctx)
        assert res_next["count"] == 3, "Remaining unreturned messages must still be unacknowledged!"

    @pytest.mark.asyncio
    async def test_string_tags_kwarg_silently_bypasses_filtering(self) -> None:
        """Verify passing tags='hardware' (singular string in 'tags' kwarg) filters properly."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        # Passing tags as a string
        res = await read_message_board(tags="hardware", tool_context=ctx)
        # Exactly 1 message returned with tag 'hardware'
        assert res["count"] == 1, "filter_tag must match 'hardware' tag cleanly"
        assert "hardware" in res["messages"][0]["tags"]

    @pytest.mark.asyncio
    async def test_multiple_tags_in_kwargs_list_matches_all_tags(self) -> None:
        """Verify that passing multiple tags in kwargs doesn't drop subsequent tags."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project})

        # Msg 1 and 5 have "physics", Msg 2 has "hardware"
        res = await read_message_board(tags=["physics", "hardware"], tool_context=ctx)
        assert res["status"] == "success"
        assert res["count"] == 3
        tags_present = {t for m in res["messages"] for t in m["tags"]}
        assert "physics" in tags_present
        assert "hardware" in tags_present

    @pytest.mark.asyncio
    async def test_mark_as_acknowledged_without_detected_agent_safe_noop(self) -> None:
        """When tool_context has no agent name (None or empty), mark_as_acknowledged is a safe no-op."""
        project = build_test_project()
        ctx = MockToolContext(state={"project_state": project}, agent_name="")
        ctx.agent.name = ""  # empty name

        res = await read_message_board(
            message_type="insight",
            mark_as_acknowledged=True,
            tool_context=ctx,
        )
        assert res["status"] == "success"
        # No crashes, and acknowledged_by remains empty
        for m in project.message_board:
            assert len(m.acknowledged_by) == 0
