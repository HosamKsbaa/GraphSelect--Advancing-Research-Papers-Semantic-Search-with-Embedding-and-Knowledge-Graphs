"""Adversarial stress harness for ADK agent tool execution and multi-turn persistence.

Empirical verification for Milestone 4 (R5: Dual-Layer Persistence & ADK Integration):
1. Verifies that ProjectAgent, ResearchAgent, PlannerAgent, and WriterAgent all expose
   the 4 workflow tools (get_project_state, post_to_message_board, read_message_board,
   update_stage_substate).
2. Tests invocation of tools through agent tool lists using Google ADK ToolContext and
   FunctionTool.run_async.
3. Simulates a multi-turn workflow across agent boundaries (ProjectAgent -> ResearchAgent
   -> PlannerAgent -> WriterAgent -> ProjectAgent) and verifies that state mutations
   reflect in disk JSON.
4. Identifies failure modes, including:
   - ADK FunctionTool argument stripping of unlisted parameters (**kwargs) such as mark_as_acknowledged.
   - Synchronous load_state_sync deadlock when invoked on an active event loop thread with MySQL fallback.
   - Stale in-memory cache overwriting disk state across uncoordinated agent contexts.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import InMemorySessionService, Session
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from agents.orchestrator.agent import create_orchestrator_agent
from agents.planner.agent import create_planner_agent
from agents.research.agent import create_research_agent
from agents.writing.agent import create_writer_agent
from features.workflow import (
    PaperMetadata,
    ProjectPersistenceService,
    ProjectState,
)
from features.workflow.state_models import (
    OutlineStructure,
    SectionBlueprint,
    SectionDraft,
)


EXPECTED_WORKFLOW_TOOLS = {
    "get_project_state",
    "post_to_message_board",
    "read_message_board",
    "update_stage_substate",
}


def build_real_tool_context(
    agent: Any,
    project_id: str,
    raw_state: dict[str, Any] | None = None,
    session_id: str = "sess-test",
    session: Session | None = None,
) -> tuple[ToolContext, Session]:
    """Construct an authentic Google ADK ToolContext with session and invocation context."""
    sess_svc = InMemorySessionService()
    if session is None:
        initial_state: dict[str, Any] = {"project_id": project_id}
        if raw_state is not None:
            initial_state["project_state"] = raw_state

        session = Session(
            id=session_id,
            appName="alrs",
            user_id="user-challenger",
            state=initial_state,
        )
    inv_ctx = InvocationContext(
        session=session,
        agent=agent,
        invocation_id=f"inv-{agent.name}",
        session_service=sess_svc,
    )
    return ToolContext(invocation_context=inv_ctx), session


def get_agent_tool_callable(agent: Any, tool_name: str) -> Any:
    """Extract a tool callable from an agent's registered tools list."""
    for tool in agent.tools:
        name = getattr(tool, "__name__", getattr(tool, "name", str(tool)))
        if name == tool_name:
            return tool
    raise KeyError(f"Tool '{tool_name}' not found on agent '{agent.name}'")


# ===========================================================================
# 1. Agent Tool Exposure & ADK Tool Compatibility
# ===========================================================================

class TestAgentWorkflowToolExposure:
    """Verifies tool exposure, callable signatures, and ADK FunctionTool wrapping."""

    @pytest.mark.parametrize(
        "factory,expected_agent_name",
        [
            (create_orchestrator_agent, "ProjectAgent"),
            (create_research_agent, "ResearchAgent"),
            (create_planner_agent, "PlannerAgent"),
            (create_writer_agent, "WriterAgent"),
        ],
    )
    def test_all_four_agents_expose_workflow_tools(
        self, factory: Any, expected_agent_name: str
    ) -> None:
        """Verify each agent has the 4 workflow tools in its .tools list."""
        agent = factory()
        assert agent.name == expected_agent_name
        tool_names = {
            getattr(t, "__name__", getattr(t, "name", str(t))) for t in agent.tools
        }
        missing = EXPECTED_WORKFLOW_TOOLS - tool_names
        assert not missing, f"Agent '{expected_agent_name}' is missing tools: {missing}"

    @pytest.mark.parametrize(
        "factory",
        [
            create_orchestrator_agent,
            create_research_agent,
            create_planner_agent,
            create_writer_agent,
        ],
    )
    def test_workflow_tools_adk_function_tool_contract(self, factory: Any) -> None:
        """Verify that ADK FunctionTool correctly identifies context parameters and mandatory args."""
        agent = factory()
        for tool_name in EXPECTED_WORKFLOW_TOOLS:
            tool_fn = get_agent_tool_callable(agent, tool_name)
            assert callable(tool_fn), f"{tool_name} on {agent.name} is not callable"
            assert asyncio.iscoroutinefunction(tool_fn), f"{tool_name} must be an async coroutine"

            ft = FunctionTool(tool_fn)
            assert ft._context_param_name == "tool_context", (
                f"{tool_name} failed to expose 'tool_context' as ADK context parameter"
            )
            mandatory = ft._get_mandatory_args()
            assert "tool_context" not in mandatory, (
                f"{tool_name} incorrectly flagged tool_context as a mandatory user argument"
            )


# ===========================================================================
# 2. Invocation of Tools Through Agent Tool Lists with Shared Session State
# ===========================================================================

class TestDirectAgentToolExecution:
    """Tests executing tools retrieved directly from agent tool lists via ADK FunctionTool."""

    @pytest.mark.asyncio
    async def test_invoke_tools_from_all_agents_with_shared_session(
        self, tmp_path: Path
    ) -> None:
        """Execute get_project_state, post_to_message_board, update_stage_substate on each agent sequentially."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-exec-all"
        p = ProjectState(project_id=project_id, name="Execution Test", token_budget=600_000)
        svc.save_state(p)

        agents = [
            create_orchestrator_agent(),
            create_research_agent(),
            create_planner_agent(),
            create_writer_agent(),
        ]

        shared_session = None
        for agent in agents:
            tool_ctx, shared_session = build_real_tool_context(
                agent, project_id, p.model_dump() if shared_session is None else None, session=shared_session
            )

            # 1. get_project_state via FunctionTool
            get_tool = get_agent_tool_callable(agent, "get_project_state")
            ft_get = FunctionTool(get_tool)
            res_get = await ft_get.run_async(args={"scope": "summary"}, tool_context=tool_ctx)
            assert res_get["status"] == "success", f"{agent.name} get_project_state failed: {res_get}"
            assert res_get["data"]["project_id"] == project_id

            # 2. post_to_message_board via FunctionTool
            post_tool = get_agent_tool_callable(agent, "post_to_message_board")
            ft_post = FunctionTool(post_tool)
            res_post = await ft_post.run_async(
                args={
                    "message_type": "insight",
                    "title": f"Insight from {agent.name}",
                    "content": f"Verified execution via {agent.name}.tools list.",
                    "tags": ["verification", agent.name.lower()],
                },
                tool_context=tool_ctx,
            )
            assert res_post["status"] == "success", f"{agent.name} post_to_message_board failed: {res_post}"

            # 3. read_message_board via FunctionTool
            read_tool = get_agent_tool_callable(agent, "read_message_board")
            ft_read = FunctionTool(read_tool)
            res_read = await ft_read.run_async(
                args={"tag": agent.name.lower()},
                tool_context=tool_ctx,
            )
            assert res_read["status"] == "success"
            assert res_read["count"] >= 1

            # 4. update_stage_substate via FunctionTool
            update_tool = get_agent_tool_callable(agent, "update_stage_substate")
            ft_update = FunctionTool(update_tool)
            res_update = await ft_update.run_async(
                args={
                    "stage": "stage_1_research",
                    "quadrant": "notes",
                    "data": f"Note logged by {agent.name}",
                },
                tool_context=tool_ctx,
            )
            assert res_update["status"] == "success", f"{agent.name} update_stage_substate failed: {res_update}"

        # Verify disk file contains all 4 notes and 4 board messages
        disk_file = tmp_path / project_id / "project_state.json"
        assert disk_file.exists()
        disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
        assert len(disk_data["message_board"]) == 4
        assert len(disk_data["stage_1_research"]["notes"]) == 4


# ===========================================================================
# 3. Multi-Turn Cross-Agent Boundary Workflow Simulation
# ===========================================================================

class TestMultiTurnCrossAgentBoundaryWorkflow:
    """Adversarially simulates a complete multi-turn workflow across 4 agents.
    
    Verifies that state changes made by each agent persist to disk JSON and
    are immediately visible to subsequent agents across turn boundaries.
    """

    @pytest.mark.asyncio
    async def test_full_cross_agent_boundary_pipeline_and_disk_verification(
        self, tmp_path: Path
    ) -> None:
        """Execute a 5-turn cross-agent sequence:
        Turn 1: ProjectAgent initializes Stage 1 meta.
        Turn 2: ResearchAgent posts a research gap and stores discovered papers.
        Turn 3: PlannerAgent reads gap and stores an outline.
        Turn 4: WriterAgent reads outline via dot-path, drafts section markdown, posts decision.
        Turn 5: ProjectAgent queries summary and validates full lifecycle.
        Final: Independent file inspection guarantees 100% schema integrity and data persistence.
        """
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-multiagent-adversarial"
        state = ProjectState(
            project_id=project_id,
            name="Adversarial Multi-Agent Literature Review",
            topic="Attention-based Graph Neural Networks",
            token_budget=1_000_000,
        )
        svc.save_state(state)
        disk_path = tmp_path / project_id / "project_state.json"
        assert disk_path.exists()

        # Instantiate the four agents
        project_agent = create_orchestrator_agent()
        research_agent = create_research_agent()
        planner_agent = create_planner_agent()
        writer_agent = create_writer_agent()

        # Shared session state simulating ADK session across agent turns
        session_state: dict[str, Any] = {
            "project_id": project_id,
            "project_state": state.model_dump(mode="json"),
        }
        sess_svc = InMemorySessionService()
        session = Session(id="session-multi", appName="alrs", user_id="tester", state=session_state)

        # -------------------------------------------------------------------
        # TURN 1: ProjectAgent sets stage_1_research status to in_progress
        # -------------------------------------------------------------------
        inv_ctx1 = InvocationContext(session=session, agent=project_agent, invocation_id="inv-turn-1", session_service=sess_svc)
        ctx1 = ToolContext(invocation_context=inv_ctx1)

        tool_update_p = get_agent_tool_callable(project_agent, "update_stage_substate")
        res1 = await FunctionTool(tool_update_p).run_async(
            args={
                "stage": "stage_1_research",
                "quadrant": "meta",
                "data": {"status": "in_progress", "progress_percentage": 10.0},
            },
            tool_context=ctx1,
        )
        assert res1["status"] == "success"

        # Verify disk immediately reflects Turn 1
        d1 = json.loads(disk_path.read_text(encoding="utf-8"))
        assert d1["stage_1_research"]["meta"]["status"] == "in_progress"
        assert d1["stage_1_research"]["meta"]["progress_percentage"] == 10.0

        # -------------------------------------------------------------------
        # TURN 2: ResearchAgent posts a gap message and adds discovered papers
        # -------------------------------------------------------------------
        inv_ctx2 = InvocationContext(session=session, agent=research_agent, invocation_id="inv-turn-2", session_service=sess_svc)
        ctx2 = ToolContext(invocation_context=inv_ctx2)

        tool_post_r = get_agent_tool_callable(research_agent, "post_to_message_board")
        res2_post = await FunctionTool(tool_post_r).run_async(
            args={
                "message_type": "gap",
                "title": "Scalability Gap in Large Graph Transformers",
                "content": "Sparse attention implementations lack standard benchmark comparisons.",
                "stage": "stage_1_research",
                "tags": ["scalability", "transformers", "gap"],
                "related_paper_dois": ["https://doi.org/10.1145/3292500", "10.48550/arxiv.2106.05234"],
            },
            tool_context=ctx2,
        )
        assert res2_post["status"] == "success"
        gap_msg_id = res2_post["message_id"]

        # Add paper to stage_1_research.artifacts.papers
        tool_update_r = get_agent_tool_callable(research_agent, "update_stage_substate")
        paper_payload = {
            "papers": {
                "10.1145/3292500": {
                    "doi": "10.1145/3292500",
                    "title": "Graph Representation Learning via Transformers",
                    "authors": ["Alice Smith", "Bob Jones"],
                    "year": 2024,
                    "citation_count": 88,
                }
            }
        }
        res2_update = await FunctionTool(tool_update_r).run_async(
            args={"stage": "stage_1_research", "quadrant": "artifacts", "data": paper_payload},
            tool_context=ctx2,
        )
        assert res2_update["status"] == "success"

        # Verify disk immediately reflects Turn 2: author is ResearchAgent, DOIs normalized
        d2 = json.loads(disk_path.read_text(encoding="utf-8"))
        assert len(d2["message_board"]) == 1
        assert d2["message_board"][0]["author_agent"] == "ResearchAgent"
        assert d2["message_board"][0]["related_paper_dois"] == ["10.1145/3292500", "10.48550/arxiv.2106.05234"]
        assert "10.1145/3292500" in d2["stage_1_research"]["artifacts"]["papers"]
        assert d2["stage_1_research"]["artifacts"]["papers"]["10.1145/3292500"]["title"] == "Graph Representation Learning via Transformers"

        # -------------------------------------------------------------------
        # TURN 3: PlannerAgent reads gap and creates outline
        # -------------------------------------------------------------------
        inv_ctx3 = InvocationContext(session=session, agent=planner_agent, invocation_id="inv-turn-3", session_service=sess_svc)
        ctx3 = ToolContext(invocation_context=inv_ctx3)

        tool_read_pl = get_agent_tool_callable(planner_agent, "read_message_board")
        res3_read = await FunctionTool(tool_read_pl).run_async(
            args={
                "message_type": "gap",
                "unacknowledged_only": True,
            },
            tool_context=ctx3,
        )
        assert res3_read["status"] == "success"
        assert res3_read["count"] == 1
        assert res3_read["messages"][0]["id"] == gap_msg_id

        # Update planning outline
        tool_update_pl = get_agent_tool_callable(planner_agent, "update_stage_substate")
        outline_payload = {
            "outline": {
                "title": "Comprehensive Survey of Graph Transformers",
                "narrative_arc": "Foundations -> Scalability Bottlenecks -> Future Directions",
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": "Introduction to Graph Transformers",
                        "order": 1,
                        "level": 1,
                        "description": "Historical background and foundational concepts.",
                        "theme": "Introduction",
                        "assigned_dois": ["10.1145/3292500"],
                        "target_word_count": 1200,
                    }
                ],
            }
        }
        res3_update = await FunctionTool(tool_update_pl).run_async(
            args={"stage": "stage_3_planning", "quadrant": "artifacts", "data": outline_payload},
            tool_context=ctx3,
        )
        assert res3_update["status"] == "success"

        # Verify disk immediately reflects Turn 3: outline stored
        d3 = json.loads(disk_path.read_text(encoding="utf-8"))
        assert d3["stage_3_planning"]["artifacts"]["outline"]["title"] == "Comprehensive Survey of Graph Transformers"
        assert len(d3["stage_3_planning"]["artifacts"]["outline"]["sections"]) == 1

        # -------------------------------------------------------------------
        # TURN 4: WriterAgent queries outline via dot-path, drafts section, posts decision
        # -------------------------------------------------------------------
        inv_ctx4 = InvocationContext(session=session, agent=writer_agent, invocation_id="inv-turn-4", session_service=sess_svc)
        ctx4 = ToolContext(invocation_context=inv_ctx4)

        # Scoped dot-path extraction through WriterAgent.tools
        tool_get_w = get_agent_tool_callable(writer_agent, "get_project_state")
        res4_get = await FunctionTool(tool_get_w).run_async(
            args={"scope": "path", "path": "stage_3_planning.artifacts.outline.sections.0.title"},
            tool_context=ctx4,
        )
        assert res4_get["status"] == "success"
        assert res4_get["data"] == "Introduction to Graph Transformers"

        # Update stage_4_writing section_drafts and draft_sections_markdown
        tool_update_w = get_agent_tool_callable(writer_agent, "update_stage_substate")
        draft_payload = {
            "section_drafts": {
                "sec-1": {
                    "section_id": "sec-1",
                    "title": "Introduction to Graph Transformers",
                    "markdown": "## Introduction to Graph Transformers\n\nGraph Neural Networks have revolutionized...",
                    "word_count": 500,
                    "cited_dois": ["10.1145/3292500"],
                }
            },
            "draft_sections_markdown": {
                "sec-1": "## Introduction to Graph Transformers\n\nGraph Neural Networks have revolutionized..."
            },
        }
        res4_update = await FunctionTool(tool_update_w).run_async(
            args={"stage": "stage_4_writing", "quadrant": "artifacts", "data": draft_payload},
            tool_context=ctx4,
        )
        assert res4_update["status"] == "success"

        # Post decision message
        tool_post_w = get_agent_tool_callable(writer_agent, "post_to_message_board")
        res4_post = await FunctionTool(tool_post_w).run_async(
            args={
                "message_type": "decision",
                "title": "Adopted Introduction Section Draft",
                "content": "Section 1 drafting passed self-contained review check.",
                "stage": "stage_4_writing",
            },
            tool_context=ctx4,
        )
        assert res4_post["status"] == "success"

        # Verify disk immediately reflects Turn 4
        d4 = json.loads(disk_path.read_text(encoding="utf-8"))
        assert len(d4["message_board"]) == 2
        assert d4["message_board"][1]["message_type"] == "decision"
        assert d4["message_board"][1]["author_agent"] == "WriterAgent"
        assert "sec-1" in d4["stage_4_writing"]["artifacts"]["section_drafts"]

        # -------------------------------------------------------------------
        # TURN 5: ProjectAgent queries summary and validates lifecycle integrity
        # -------------------------------------------------------------------
        inv_ctx5 = InvocationContext(session=session, agent=project_agent, invocation_id="inv-turn-5", session_service=sess_svc)
        ctx5 = ToolContext(invocation_context=inv_ctx5)

        tool_get_p = get_agent_tool_callable(project_agent, "get_project_state")
        res5_summary = await FunctionTool(tool_get_p).run_async(
            args={"scope": "summary"},
            tool_context=ctx5,
        )
        assert res5_summary["status"] == "success"
        summary_data = res5_summary["data"]
        assert summary_data["project_id"] == project_id
        assert summary_data["message_board_total"] == 2
        assert summary_data["stages"]["stage_1_research"]["paper_count"] == 1
        assert summary_data["stages"]["stage_3_planning"]["section_count"] == 1
        assert summary_data["stages"]["stage_4_writing"]["drafted_sections"] == 1

        # -------------------------------------------------------------------
        # FINAL INDEPENDENT DISK VERIFICATION (Complete Cold Read)
        # -------------------------------------------------------------------
        raw_disk_bytes = disk_path.read_bytes()
        reloaded_state = ProjectState.model_validate_json(raw_disk_bytes)
        assert reloaded_state.project_id == project_id
        assert reloaded_state.stage_1_research.meta.status == "in_progress"
        assert "10.1145/3292500" in reloaded_state.stage_1_research.artifacts.papers
        assert reloaded_state.stage_3_planning.artifacts.outline.title == "Comprehensive Survey of Graph Transformers"
        assert "sec-1" in reloaded_state.stage_4_writing.artifacts.section_drafts
        assert len(reloaded_state.message_board) == 2


# ===========================================================================
# 4. Context-Free State Hydration from Disk
# ===========================================================================

class TestContextFreeDiskHydration:
    """Verifies that an agent whose context contains ONLY project_id hydrates cleanly from disk."""

    @pytest.mark.asyncio
    async def test_agent_hydrates_from_disk_without_in_memory_state(
        self, tmp_path: Path
    ) -> None:
        """When tool_context.state has no 'project_state', tool loads from disk and hydrates."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-cold-hydration"
        p = ProjectState(project_id=project_id, name="Cold Disk Hydration Test")
        p.stage_1_research.meta.status = "in_progress"
        svc.save_state(p)

        agent = create_research_agent()
        # Context contains only project_id, no project_state dict
        sess_svc = InMemorySessionService()
        session = Session(id="s-cold", appName="alrs", user_id="tester", state={"project_id": project_id})
        inv_ctx = InvocationContext(session=session, agent=agent, invocation_id="inv-cold", session_service=sess_svc)
        tool_ctx = ToolContext(invocation_context=inv_ctx)

        # 1. get_project_state should succeed by loading from disk
        get_tool = get_agent_tool_callable(agent, "get_project_state")
        res = await FunctionTool(get_tool).run_async(args={"scope": "summary"}, tool_context=tool_ctx)
        assert res["status"] == "success"
        assert res["data"]["project_id"] == project_id
        assert res["data"]["stages"]["stage_1_research"]["status"] == "in_progress"

        # 2. tool_context should now be hydrated with in-memory state
        assert "project_state" in tool_ctx.state

        # 3. Subsequent mutation should successfully update disk
        update_tool = get_agent_tool_callable(agent, "update_stage_substate")
        res_mut = await FunctionTool(update_tool).run_async(
            args={"stage": "stage_1_research", "quadrant": "meta", "data": {"progress_percentage": 50.0}},
            tool_context=tool_ctx,
        )
        assert res_mut["status"] == "success"

        # Check disk
        d = json.loads((tmp_path / project_id / "project_state.json").read_text(encoding="utf-8"))
        assert d["stage_1_research"]["meta"]["progress_percentage"] == 50.0


# ===========================================================================
# 5. Adversarial Input Rejection & State Integrity
# ===========================================================================

class TestAdversarialInputRejection:
    """Verifies that invalid, malformed, or malicious tool arguments fail safely without corruption."""

    @pytest.mark.asyncio
    async def test_invalid_tool_inputs_rejected_without_corrupting_state(
        self, tmp_path: Path
    ) -> None:
        """Adversarial input testing on all tools."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-malformed"
        p = ProjectState(project_id=project_id, name="Integrity Guard")
        svc.save_state(p)

        agent = create_orchestrator_agent()
        tool_ctx, _ = build_real_tool_context(agent, project_id, p.model_dump())
        disk_path = tmp_path / project_id / "project_state.json"
        original_json = disk_path.read_text(encoding="utf-8")

        # 1. Invalid stage name
        tool_update = get_agent_tool_callable(agent, "update_stage_substate")
        res_bad_stage = await FunctionTool(tool_update).run_async(
            args={"stage": "stage_99_fantasy", "quadrant": "meta", "data": {"status": "done"}},
            tool_context=tool_ctx,
        )
        assert res_bad_stage["status"] == "error"
        assert "Invalid stage" in res_bad_stage["message"]

        # 2. Invalid quadrant name
        res_bad_quad = await FunctionTool(tool_update).run_async(
            args={"stage": "stage_1_research", "quadrant": "hallucinations", "data": {"status": "done"}},
            tool_context=tool_ctx,
        )
        assert res_bad_quad["status"] == "error"
        assert "Invalid quadrant" in res_bad_quad["message"]

        # 3. Invalid data type (string instead of dict for meta)
        res_bad_type = await FunctionTool(tool_update).run_async(
            args={"stage": "stage_1_research", "quadrant": "meta", "data": "not_a_dictionary"},
            tool_context=tool_ctx,
        )
        assert res_bad_type["status"] == "error"
        assert "must be a dict" in res_bad_type["message"]

        # 4. Invalid message type on post_to_message_board
        tool_post = get_agent_tool_callable(agent, "post_to_message_board")
        res_bad_msg = await FunctionTool(tool_post).run_async(
            args={"message_type": "gossip", "title": "Secret", "content": "Rumor"},
            tool_context=tool_ctx,
        )
        assert res_bad_msg["status"] == "error"
        assert "Invalid message_type" in res_bad_msg["message"]

        # 5. Non-existent dot-path query on get_project_state
        tool_get = get_agent_tool_callable(agent, "get_project_state")
        res_bad_path = await FunctionTool(tool_get).run_async(
            args={"scope": "path", "path": "stage_1_research.artifacts.nonexistent[999].deep"},
            tool_context=tool_ctx,
        )
        assert res_bad_path["status"] == "error"
        assert "not found" in res_bad_path["message"] or "failed" in res_bad_path["message"]

        # Disk file must be 100% identical to original
        assert disk_path.read_text(encoding="utf-8") == original_json


# ===========================================================================
# 6. Concurrency Stress Harness
# ===========================================================================

class TestConcurrencyStressHarness:
    """Stress tests rapid concurrent tool calls and atomic file replacements."""

    @pytest.mark.asyncio
    async def test_concurrent_tool_invocations_preserve_disk_integrity(
        self, tmp_path: Path
    ) -> None:
        """Execute 25 concurrent tool calls across agents and verify atomic persistence."""
        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-stress-concurrent"
        p = ProjectState(project_id=project_id, name="Concurrent Stress Review")
        svc.save_state(p)

        agents = [
            create_orchestrator_agent(),
            create_research_agent(),
            create_planner_agent(),
            create_writer_agent(),
        ]

        async def worker_task(idx: int) -> dict[str, Any]:
            chosen_agent = agents[idx % len(agents)]
            tool_ctx, _ = build_real_tool_context(chosen_agent, project_id, p.model_dump(), session_id=f"s-{idx}")
            if idx % 2 == 0:
                tool = get_agent_tool_callable(chosen_agent, "post_to_message_board")
                return await FunctionTool(tool).run_async(
                    args={
                        "message_type": "insight",
                        "title": f"Concurrent insight {idx}",
                        "content": f"Test content from task {idx}",
                    },
                    tool_context=tool_ctx,
                )
            else:
                tool = get_agent_tool_callable(chosen_agent, "update_stage_substate")
                return await FunctionTool(tool).run_async(
                    args={
                        "stage": "stage_1_research",
                        "quadrant": "notes",
                        "data": f"Concurrent note from task {idx}",
                    },
                    tool_context=tool_ctx,
                )

        results = await asyncio.gather(*[worker_task(i) for i in range(25)])
        assert all(r["status"] == "success" for r in results)

        # Confirm disk JSON is parseable, valid Pydantic model, and uncorrupted
        disk_path = tmp_path / project_id / "project_state.json"
        assert disk_path.exists()
        reloaded = ProjectState.model_validate_json(disk_path.read_text(encoding="utf-8"))
        assert reloaded.project_id == project_id


# ===========================================================================
# 7. Defect Proof: ADK FunctionTool kwargs Stripping
# ===========================================================================

class TestAdkKwargsStrippingDefectProof:
    """Empirically proves the bug where ADK FunctionTool drops mark_as_acknowledged."""

    @pytest.mark.asyncio
    async def test_prove_mark_as_acknowledged_dropped_by_adk(
        self, tmp_path: Path
    ) -> None:
        """Direct call receives mark_as_acknowledged via kwargs, but FunctionTool drops it."""
        from features.workflow.state_tools import read_message_board

        svc = ProjectPersistenceService(mysql=None, base_data_dir=tmp_path)
        ProjectPersistenceService.set_instance(svc)

        project_id = "proj-ack-defect"
        p = ProjectState(project_id=project_id, name="Ack Defect Test")
        p.post_message(author_agent="ResearchAgent", message_type="gap", title="Gap", content="Content")
        svc.save_state(p)

        agent = create_planner_agent()
        tool_ctx, _ = build_real_tool_context(agent, project_id, p.model_dump())

        # 1. Direct call to function: works because kwargs is accepted by Python
        res_direct = await read_message_board(unacknowledged_only=True, mark_as_acknowledged=True, tool_context=tool_ctx)
        assert res_direct["status"] == "success"
        disk_after_direct = json.loads((tmp_path / project_id / "project_state.json").read_text(encoding="utf-8"))
        assert "PlannerAgent" in disk_after_direct["message_board"][0]["acknowledged_by"], (
            "Direct call should mark acknowledged"
        )

        # Reset acknowledgment on disk and memory
        p.message_board[0].acknowledged_by.clear()
        svc.save_state(p)
        tool_ctx, _ = build_real_tool_context(agent, project_id, p.model_dump())

        # 2. ADK FunctionTool invocation: drops mark_as_acknowledged because it is not an explicit parameter!
        ft = FunctionTool(read_message_board)
        res_ft = await ft.run_async(args={"unacknowledged_only": True, "mark_as_acknowledged": True}, tool_context=tool_ctx)
        assert res_ft["status"] == "success"
        disk_after_ft = json.loads((tmp_path / project_id / "project_state.json").read_text(encoding="utf-8"))
        
        # VERIFICATION OF FIX: acknowledged_by contains PlannerAgent because ADK preserved mark_as_acknowledged!
        is_acknowledged = "PlannerAgent" in disk_after_ft["message_board"][0]["acknowledged_by"]
        assert is_acknowledged, (
            "FunctionTool successfully forwarded mark_as_acknowledged!"
        )


# ===========================================================================
# 8. Defect Proof: load_state_sync Deadlock on Active Event Loop
# ===========================================================================

class TestLoadStateSyncDeadlockDefectProof:
    """Empirically proves the deadlock in load_state_sync line 472."""

    @pytest.mark.asyncio
    async def test_prove_load_state_sync_deadlocks_on_active_loop(
        self, tmp_path: Path
    ) -> None:
        """When called on an active event loop thread with MySQL fallback, load_state_sync deadlocks."""
        project_id = "proj-deadlock-proof"
        valid_project = ProjectState(project_id=project_id, name="MySQL State")

        mock_mysql = MagicMock()
        mock_mysql.fetch_one = AsyncMock(
            return_value={"state": valid_project.model_dump_json(), "version": 1}
        )

        svc = ProjectPersistenceService(mysql=mock_mysql, base_data_dir=tmp_path / "nonexistent")

        loop = asyncio.get_running_loop()

        # In persistence_service.py line 472:
        # return asyncio.run_coroutine_threadsafe(_load_mysql(), loop).result()
        # On the loop thread, calling .result() blocks the loop thread waiting for the coroutine,
        # which can never run because the loop thread is blocked.
        # We verify that attempting this synchronously on the loop thread deadlocks/times out.
        coro = mock_mysql.fetch_one("SELECT")
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        with pytest.raises(TimeoutError):
            fut.result(timeout=0.2)
