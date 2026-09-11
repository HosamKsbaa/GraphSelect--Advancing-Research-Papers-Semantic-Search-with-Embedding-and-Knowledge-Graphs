"""Unit and integration tests for SearchSnowballAgent tool registration (T050 / Milestone M6).

Verifies that the 4 enhancement tools are properly registered into SearchSnowballAgent:
1. ingest_user_paper_tool
2. confirm_title_ingestion_tool
3. svpl_multi_hop_discovery_tool
4. run_autonomous_gap_remediation_tool

Conforms to Constitution v2.2.1 (C7, C9, A28, A33).
"""
from __future__ import annotations

import inspect
from typing import Any
import pytest

from agents.stage2_acquisition.agent import (
    SearchSnowballAgent,
    create_search_snowball_agent,
    create_stage2_acquisition_workflow,
)
from agents.tools.autonomous_enhancement_tools import (
    confirm_title_ingestion_tool,
    ingest_user_paper_tool,
    run_autonomous_gap_remediation_tool,
    svpl_multi_hop_discovery_tool,
)


def _get_agent_tool_names(agent: Any) -> list[str]:
    """Extract tool function names from an agent."""
    return [
        t.__name__ if hasattr(t, "__name__") else getattr(t, "name", "")
        for t in agent.tools
    ]


def test_search_snowball_agent_has_enhancement_tools() -> None:
    """Verify SearchSnowballAgent contains all 4 enhancement tools."""
    agent = create_search_snowball_agent()
    names = _get_agent_tool_names(agent)
    assert "ingest_user_paper_tool" in names
    assert "confirm_title_ingestion_tool" in names
    assert "svpl_multi_hop_discovery_tool" in names
    assert "run_autonomous_gap_remediation_tool" in names


def test_search_snowball_agent_preserves_baseline_tools() -> None:
    """Verify SearchSnowballAgent still has baseline workflow and state tools."""
    agent = create_search_snowball_agent()
    names = _get_agent_tool_names(agent)
    assert "run_alrs_snowballing_tool" in names
    assert "get_project_state" in names
    assert "post_to_message_board" in names
    assert "read_message_board" in names
    assert "complete_stage" in names
    assert len(agent.tools) == 9


def test_enhancement_tools_are_callable_and_async() -> None:
    """Verify registered enhancement tools are callable async functions."""
    tools = [
        ingest_user_paper_tool,
        confirm_title_ingestion_tool,
        svpl_multi_hop_discovery_tool,
        run_autonomous_gap_remediation_tool,
    ]
    for t in tools:
        assert callable(t)
        assert inspect.iscoroutinefunction(t)


def test_search_snowball_agent_alias_and_metadata() -> None:
    """Verify SearchSnowballAgent factory alias and descriptive metadata."""
    agent = SearchSnowballAgent()
    assert agent.name == "SearchSnowballAgent"
    assert "ingestion" in agent.instruction.lower() or "ingestion" in agent.description.lower()
    assert "gap" in agent.instruction.lower() or "gap" in agent.description.lower()
    assert agent.output_key == "snowball_result"


def test_stage2_workflow_contains_configured_agent() -> None:
    """Verify Stage 2 SequentialAgent workflow contains SearchSnowballAgent with tools."""
    workflow = create_stage2_acquisition_workflow()
    builder = workflow.sub_agents[0]
    names = _get_agent_tool_names(builder)
    assert "ingest_user_paper_tool" in names
    assert "svpl_multi_hop_discovery_tool" in names
    assert "run_autonomous_gap_remediation_tool" in names
