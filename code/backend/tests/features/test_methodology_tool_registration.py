"""Unit and integration tests for MethodologyArchitect tool registration (T051 / Milestone M6).

Verifies that generate_section_synthesis_matrix_tool is registered into MethodologyArchitect:
Conforms to Constitution v2.2.1 (C7, C9, A28, A33).
"""
from __future__ import annotations

import inspect
from typing import Any
import pytest

from agents.stage4_synthesis.agent import (
    MethodologyArchitect,
    create_methodology_architect_agent,
    create_stage4_synthesis_workflow,
)
from agents.tools.autonomous_enhancement_tools import (
    generate_section_synthesis_matrix_tool,
)


def _get_agent_tool_names(agent: Any) -> list[str]:
    """Extract tool function names from an agent."""
    return [
        t.__name__ if hasattr(t, "__name__") else getattr(t, "name", "")
        for t in agent.tools
    ]


def test_methodology_architect_has_matrix_tool() -> None:
    """Verify MethodologyArchitect contains generate_section_synthesis_matrix_tool."""
    agent = create_methodology_architect_agent()
    names = _get_agent_tool_names(agent)
    assert "generate_section_synthesis_matrix_tool" in names


def test_methodology_architect_preserves_baseline_tools() -> None:
    """Verify MethodologyArchitect preserves baseline comparison and state tools."""
    agent = create_methodology_architect_agent()
    names = _get_agent_tool_names(agent)
    assert "synthesize_comparison_matrix_tool" in names
    assert "get_project_state" in names
    assert "post_to_message_board" in names
    assert "read_message_board" in names
    assert "complete_stage" in names
    assert len(agent.tools) == 6


def test_matrix_tool_is_callable_and_async() -> None:
    """Verify registered matrix tool is a callable async coroutine function."""
    assert callable(generate_section_synthesis_matrix_tool)
    assert inspect.iscoroutinefunction(generate_section_synthesis_matrix_tool)


def test_methodology_architect_alias_and_metadata() -> None:
    """Verify MethodologyArchitect factory alias and descriptive metadata."""
    agent = MethodologyArchitect()
    assert agent.name == "MethodologyArchitect"
    assert "section" in agent.instruction.lower() or "section" in agent.description.lower()
    assert agent.output_key == "synthesis_result"


def test_stage4_workflow_contains_configured_agent() -> None:
    """Verify Stage 4 SequentialAgent workflow contains MethodologyArchitect with matrix tool."""
    workflow = create_stage4_synthesis_workflow()
    builder = workflow.sub_agents[0]
    names = _get_agent_tool_names(builder)
    assert "generate_section_synthesis_matrix_tool" in names
    assert "synthesize_comparison_matrix_tool" in names
