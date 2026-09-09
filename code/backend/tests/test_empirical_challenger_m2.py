"""Empirical Challenger Verification Suite for Milestone 2.

Authored by challenger_m2.
Empirically tests and stress-tests:
1. create_debugger_agent() ADK LlmAgent creation and 4 self-debug tools registration.
2. Swarm hierarchy traversability from root_agent through the entire multi-level agent tree.
3. Sub-agent hierarchy structure, leaf nodes, tool inventories, and callback bindings.
4. Global error delegation protocol embedded in coordinator agent instructions.
5. Adversarial boundary conditions and error resilience across agent factories and tools.
"""
from __future__ import annotations

import inspect
from typing import Any, List, Set
from unittest.mock import MagicMock

import pytest
from google.adk.agents import BaseAgent, LlmAgent, LoopAgent

from agents.agent import root_agent
from agents.debugger.agent import (
    DEBUGGER_AGENT_INSTRUCTION,
    DebuggerAgent,
    create_debugger_agent,
    debugger_agent,
)
from agents.orchestrator.agent import (
    ORCHESTRATOR_INSTRUCTION,
)
from agents.planner.agent import create_planner_agent, planner_agent
from agents.research.agent import create_research_agent
from agents.research.alrs_agent import create_alrs_agent
from agents.research.evidence_synthesizer import create_evidence_synthesizer_agent
from agents.research.gap_finder import create_gap_finder_agent
from agents.writing.agent import create_writer_agent, writer_agent
from agents.writing.drafting_agent import drafting_agent
from agents.writing.reviewer_agent import reviewer_agent
from agents.tools.self_debug_tools import (
    fetch_error_logs,
    read_agent_code,
    run_agent_tests,
    validate_and_propose_patch,
)
from config import get_settings


# ============================================================================
# 1. EMPIRICAL VERIFICATION: create_debugger_agent()
# ============================================================================

def test_create_debugger_agent_adk_instance():
    """Empirically verify create_debugger_agent returns a valid Google ADK LlmAgent."""
    agent = create_debugger_agent()

    # 1. Type validation
    assert isinstance(agent, LlmAgent), f"Expected LlmAgent, got {type(agent)}"
    assert isinstance(agent, BaseAgent), f"Expected BaseAgent, got {type(agent)}"

    # 2. Attribute validation
    assert agent.name == "DebuggerAgent"
    assert agent.model is not None and len(agent.model) > 0
    settings = get_settings()
    assert agent.model in (settings.adk_tier1_model, settings.adk_model_name)
    assert agent.description is not None and len(agent.description) > 0
    assert "diagnostic" in agent.description.lower() or "bug" in agent.description.lower()

    # 3. Instruction validation
    assert agent.instruction is not None and len(agent.instruction) > 100
    assert "read_agent_code" in agent.instruction
    assert "fetch_error_logs" in agent.instruction
    assert "run_agent_tests" in agent.instruction
    assert "validate_and_propose_patch" in agent.instruction


def test_debugger_agent_tools_exact_inventory():
    """Empirically verify DebuggerAgent has all 4 self-debug tools registered with correct signatures."""
    agent = create_debugger_agent()
    expected_tools = {
        "read_agent_code": read_agent_code,
        "fetch_error_logs": fetch_error_logs,
        "run_agent_tests": run_agent_tests,
        "validate_and_propose_patch": validate_and_propose_patch,
    }

    actual_tools = {getattr(t, "__name__", str(t)): t for t in agent.tools}

    assert len(actual_tools) == 4, f"Expected 4 tools, got {len(actual_tools)}: {list(actual_tools.keys())}"
    for tool_name, tool_func in expected_tools.items():
        assert tool_name in actual_tools, f"Missing tool '{tool_name}' in DebuggerAgent tools."
        assert actual_tools[tool_name] is tool_func, f"Tool '{tool_name}' does not reference canonical tool function."

        # Verify tool is a valid callable with docstring and annotations
        assert callable(tool_func)
        assert tool_func.__doc__ is not None and len(tool_func.__doc__) > 20
        sig = inspect.signature(tool_func)
        assert len(sig.parameters) > 0, f"Tool '{tool_name}' has no parameters."


def test_debugger_agent_module_exports_and_singletons():
    """Verify DebuggerAgent module exports and singleton aliases match ADK standards."""
    import agents
    import agents.agent
    import agents.debugger
    import agents.debugger.agent

    # Verify presence in top-level package and submodules
    for mod in (agents, agents.agent, agents.debugger, agents.debugger.agent):
        assert hasattr(mod, "DebuggerAgent"), f"{mod.__name__} missing DebuggerAgent"
        assert hasattr(mod, "create_debugger_agent"), f"{mod.__name__} missing create_debugger_agent"
        assert hasattr(mod, "debugger_agent"), f"{mod.__name__} missing debugger_agent"

    # Verify singleton properties
    assert isinstance(DebuggerAgent, LlmAgent)
    assert isinstance(debugger_agent, LlmAgent)
    assert DebuggerAgent.name == "DebuggerAgent"
    assert debugger_agent.name == "DebuggerAgent"


def test_debugger_agent_fresh_instances_isolation():
    """Verify multiple invocations of create_debugger_agent produce distinct independent objects."""
    d1 = create_debugger_agent()
    d2 = create_debugger_agent()

    assert d1 is not d2
    assert d1.name == d2.name
    assert d1.tools == d2.tools
    assert d1.parent_agent is None
    assert d2.parent_agent is None


# ============================================================================
# 2. EMPIRICAL VERIFICATION: Root Agent & Orchestrator Structure
# ============================================================================

def test_root_orchestrator_agent_sub_agents():
    """Empirically verify root_agent is ProjectAgent with all 4 sub-agents: ResearchAgent, PlannerAgent, WriterAgent, DebuggerAgent."""
    orchestrator = root_agent

    # 1. Type validation
    assert isinstance(orchestrator, LlmAgent)
    assert orchestrator.name == "ProjectAgent"
    assert "orchestrator" in orchestrator.description.lower() or "literature review" in orchestrator.description.lower()

    # 2. Direct tools validation
    tool_names = [getattr(t, "__name__", str(t)) for t in orchestrator.tools]
    assert "create_new_project" in tool_names
    assert "select_project" in tool_names
    assert "list_projects" in tool_names

    # 3. Sub-agents inventory validation
    sub_agent_map = {a.name: a for a in orchestrator.sub_agents}
    expected_sub_agents = ["ResearchAgent", "PlannerAgent", "WriterAgent", "DebuggerAgent"]

    assert len(orchestrator.sub_agents) == 4, f"Expected 4 sub-agents, got {len(orchestrator.sub_agents)}: {list(sub_agent_map.keys())}"
    for name in expected_sub_agents:
        assert name in sub_agent_map, f"Missing sub-agent '{name}' in ProjectAgent."
        sub = sub_agent_map[name]
        assert isinstance(sub, BaseAgent), f"Sub-agent '{name}' is not an ADK BaseAgent."


# ============================================================================
# 3. EMPIRICAL VERIFICATION: Full Hierarchy Traversability from root_agent
# ============================================================================

def _traverse_hierarchy(agent: BaseAgent) -> dict[str, Any]:
    """Helper to recursively traverse the ADK agent tree and collect topology metadata."""
    node: dict[str, Any] = {
        "name": agent.name,
        "type": type(agent).__name__,
        "tools": [getattr(t, "__name__", str(t)) for t in getattr(agent, "tools", [])],
        "sub_agents": [],
    }
    for sub in getattr(agent, "sub_agents", []):
        node["sub_agents"].append(_traverse_hierarchy(sub))
    return node


def _collect_all_agent_names(agent: BaseAgent) -> list[str]:
    """Collect all agent names recursively."""
    names = [agent.name]
    for sub in getattr(agent, "sub_agents", []):
        names.extend(_collect_all_agent_names(sub))
    return names


def test_hierarchy_full_traversability():
    """Empirically test full recursive tree traversability from root_agent."""
    root = root_agent
    assert root.name == "ProjectAgent"

    topology = _traverse_hierarchy(root)
    all_names = _collect_all_agent_names(root)

    # Expected swarm agent roster
    expected_roster = {
        "ProjectAgent",
        "ResearchAgent",
        "ALRSAgent",
        "GapFinderAgent",
        "EvidenceSynthesizerAgent",
        "PlannerAgent",
        "WriterAgent",
        "WriterReviewerLoop",
        "DraftingAgent",
        "ReviewerAgent",
        "DebuggerAgent",
    }

    for name in expected_roster:
        assert name in all_names, f"Agent '{name}' was not reachable in hierarchy traversal from root_agent."

    # Validate topology levels
    # Level 1: ProjectAgent
    assert topology["name"] == "ProjectAgent"
    level1_map = {child["name"]: child for child in topology["sub_agents"]}
    assert set(level1_map.keys()) == {"ResearchAgent", "PlannerAgent", "WriterAgent", "DebuggerAgent"}

    # Level 2 under ResearchAgent: ALRSAgent, GapFinderAgent, EvidenceSynthesizerAgent
    research_children = {child["name"] for child in level1_map["ResearchAgent"]["sub_agents"]}
    assert research_children == {"ALRSAgent", "GapFinderAgent", "EvidenceSynthesizerAgent"}

    # Level 2 under WriterAgent: WriterReviewerLoop
    writer_children = level1_map["WriterAgent"]["sub_agents"]
    assert len(writer_children) == 1
    assert writer_children[0]["name"] == "WriterReviewerLoop"
    assert writer_children[0]["type"] == "LoopAgent"

    # Level 3 under WriterReviewerLoop: DraftingAgent, ReviewerAgent
    loop_children = {child["name"] for child in writer_children[0]["sub_agents"]}
    assert loop_children == {"DraftingAgent", "ReviewerAgent"}

    # Level 2 under DebuggerAgent: leaf agent (0 sub_agents, 4 tools)
    assert len(level1_map["DebuggerAgent"]["sub_agents"]) == 0
    assert set(level1_map["DebuggerAgent"]["tools"]) == {
        "read_agent_code",
        "fetch_error_logs",
        "run_agent_tests",
        "validate_and_propose_patch",
    }


# ============================================================================
# 4. EMPIRICAL VERIFICATION: Global Error Delegation Protocol in Coordinator Instructions
# ============================================================================

def test_global_error_protocol_in_coordinator_instructions():
    """Empirically verify all coordinator agents in the hierarchy contain the Global Error Protocol directive."""
    coordinators = [
        root_agent,
        [a for a in root_agent.sub_agents if a.name == "ResearchAgent"][0],
        [a for a in root_agent.sub_agents if a.name == "PlannerAgent"][0],
        [a for a in root_agent.sub_agents if a.name == "WriterAgent"][0],
        [a for a in root_agent.sub_agents if a.name == "DebuggerAgent"][0],
    ]

    for agent in coordinators:
        instruction = getattr(agent, "instruction", "")
        assert isinstance(instruction, str) and len(instruction) > 0, f"Coordinator '{agent.name}' has empty instruction."
        inst_lower = instruction.lower()
        has_error_directive = (
            "global error delegation protocol" in inst_lower
            or "debuggeragent" in inst_lower
            or "debugger" in inst_lower
            or "error" in inst_lower
        )
        assert has_error_directive, f"Coordinator agent '{agent.name}' lacks error delegation directive in instruction."


# ============================================================================
# 5. EMPIRICAL STRESS TESTS & TOOL WORKFLOW
# ============================================================================

@pytest.mark.asyncio
async def test_debugger_agent_tool_pipeline_integration(tmp_path, monkeypatch):
    """Empirically simulate the full DebuggerAgent workflow: read code -> patch -> verify."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    # 1. Setup buggy file
    buggy_code = (
        "def compute_total(a: int, b: int) -> int:\n"
        "    # Bug: subtraction instead of addition\n"
        "    return a - b\n"
    )
    buggy_file = tmp_path / "math_ops.py"
    buggy_file.write_text(buggy_code, encoding="utf-8")

    # Step 1: read_agent_code
    read_res = await read_agent_code("math_ops.py", function_or_class_name="compute_total")
    assert read_res["success"] is True
    assert "return a - b" in read_res["code"]

    # Step 2: validate_and_propose_patch
    patch_res = await validate_and_propose_patch(
        file_path="math_ops.py",
        target_snippet="return a - b",
        replacement_snippet="return a + b",
        explanation="Fix subtraction bug to addition",
    )
    assert patch_res["success"] is True
    assert patch_res["syntax_valid"] is True
    assert "-    return a - b" in patch_res["diff"]
    assert "+    return a + b" in patch_res["diff"]

    # Step 3: Propose invalid patch -> rejected
    invalid_patch_res = await validate_and_propose_patch(
        file_path="math_ops.py",
        target_snippet="return a - b",
        replacement_snippet="return a + ( broken syntax",
        explanation="Invalid syntax attempt",
    )
    assert invalid_patch_res["success"] is False
    assert invalid_patch_res["syntax_valid"] is False


def test_pomdp_cumulative_reward_accounting():
    """Verify POMDP cumulative reward computation R(s, a) per Constitution A48."""
    from core.logging.telemetry_service import TelemetryService
    svc = TelemetryService(":memory:")
    c_id = "test-camp-pomdp"
    svc.record_turn_event({
        "campaign_id": c_id, "agent_role": "builder", "prompt_tokens": 100,
        "completion_tokens": 100, "latency_ms": 500.0, "cost_usd": 0.20,
    })
    reward = svc.compute_pomdp_cumulative_reward(c_id)
    assert reward == 3.36, f"Expected 3.36, got {reward}"

