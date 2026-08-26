"""Unit and integration tests for autonomous writing and planning tools in ALRS v2.

Covers:
    - DraftingAgent tools (get_paper_abstracts, draft_section)
    - ReviewerAgent tools (review_section, exit_loop)
    - WriterAgent and WriterReviewerLoop configuration
    - PlannerAgent tools (get_project_summary, get_ranked_papers, generate_outline)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.planner.agent import create_planner_agent, planner_agent
from agents.planner.tools.outline_tools import (
    generate_outline,
    get_project_summary,
    get_ranked_papers,
)
from agents.writing.agent import create_writer_agent, writer_agent, writer_reviewer_loop
from agents.writing.drafting_agent import drafting_agent
from agents.writing.reviewer_agent import exit_loop, reviewer_agent
from agents.writing.tools.review_tools import review_section
from agents.writing.tools.writing_tools import draft_section, get_paper_abstracts


class DummyToolContext:
    """Mock ADK ToolContext providing state and actions."""

    def __init__(self, state: dict | None = None) -> None:
        self.state = state if state is not None else {}
        self.actions = MagicMock()
        self.actions.escalate = False
        self.actions.skip_summarization = False


# ============================================================================
# Writing Tools Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_paper_abstracts_tool():
    """Test get_paper_abstracts delegates to writing service and returns paper abstracts."""
    mock_service = AsyncMock()
    mock_service.get_paper_abstracts.return_value = {
        "papers": [
            {
                "doi": "10.1000/1",
                "title": "Attention Is All You Need",
                "abstract": "The dominant sequence transduction models...",
                "year": 2017,
                "source": "NeurIPS",
            }
        ]
    }

    ctx = DummyToolContext(state={"project_id": "proj-123"})

    with patch.object(ServiceRegistry, "writing_service", mock_service):
        res = await get_paper_abstracts(["10.1000/1"], ctx)  # type: ignore[arg-type]

    assert "papers" in res
    assert len(res["papers"]) == 1
    assert res["papers"][0]["doi"] == "10.1000/1"
    mock_service.get_paper_abstracts.assert_awaited_once_with("proj-123", ["10.1000/1"])


@pytest.mark.asyncio
async def test_draft_section_tool_updates_state():
    """Test draft_section generates draft and stores markdown in tool_context.state['section_drafts']."""
    mock_service = AsyncMock()
    mock_service.draft_section.return_value = {
        "section_title": "Background",
        "markdown": "## Background\n\nTransformers revolutionized NLP (10.1000/1).",
        "word_count": 8,
        "cited_dois": ["10.1000/1"],
        "saved_path": "/tmp/drafts/background.md",
    }

    ctx = DummyToolContext(state={"project_id": "proj-123"})

    with patch.object(ServiceRegistry, "writing_service", mock_service):
        res = await draft_section(
            section_title="Background",
            section_description="Overview of transformers",
            paper_dois=["10.1000/1"],
            target_level="master",
            tool_context=ctx,  # type: ignore[arg-type]
        )

    assert res["section_title"] == "Background"
    assert "section_drafts" in ctx.state
    assert ctx.state["section_drafts"]["Background"] == res["markdown"]


@pytest.mark.asyncio
async def test_draft_section_tool_missing_context_or_project():
    """Test draft_section fails gracefully when ToolContext or project_id is missing."""
    res_no_ctx = await draft_section("Title", "Desc", ["10.1000/1"], tool_context=None)  # type: ignore[arg-type]
    assert "error" in res_no_ctx

    ctx_no_pid = DummyToolContext(state={})
    res_no_pid = await draft_section("Title", "Desc", ["10.1000/1"], tool_context=ctx_no_pid)  # type: ignore[arg-type]
    assert "error" in res_no_pid


@pytest.mark.asyncio
async def test_review_section_tool_updates_state():
    """Test review_section executes review and stores last_review in tool_context.state."""
    mock_service = AsyncMock()
    mock_service.review_section.return_value = {
        "approved": True,
        "scores": {
            "citation_coverage": 5,
            "coherence": 5,
            "synthesis": 4,
            "academic_tone": 5,
            "completeness": 5,
        },
        "feedback": ["Excellent synthesis across transformer architectures."],
        "missing_citations": [],
        "hallucinated_citations": [],
    }

    ctx = DummyToolContext(state={"project_id": "proj-123"})

    with patch.object(ServiceRegistry, "writing_service", mock_service):
        res = await review_section(
            section_title="Background",
            draft_markdown="## Background\n\nTransformers are effective (10.1000/1).",
            assigned_dois=["10.1000/1"],
            tool_context=ctx,  # type: ignore[arg-type]
        )

    assert res["approved"] is True
    assert "last_review" in ctx.state
    assert ctx.state["last_review"]["approved"] is True


def test_exit_loop_tool_escalates_action():
    """Test exit_loop sets escalate and skip_summarization to True on ToolContext."""
    ctx = DummyToolContext()
    res = exit_loop(ctx)  # type: ignore[arg-type]

    assert res == {"status": "loop_exited"}
    assert ctx.actions.escalate is True
    assert ctx.actions.skip_summarization is True


# ============================================================================
# Agent Configuration Tests
# ============================================================================

def test_writer_reviewer_loop_configuration():
    """Test WriterReviewerLoop has drafting_agent and reviewer_agent with max_iterations=3."""
    assert writer_reviewer_loop.name == "WriterReviewerLoop"
    assert writer_reviewer_loop.max_iterations == 3
    assert len(writer_reviewer_loop.sub_agents) == 2
    assert writer_reviewer_loop.sub_agents[0].name == "DraftingAgent"
    assert writer_reviewer_loop.sub_agents[1].name == "ReviewerAgent"


def test_writer_agent_configuration():
    """Test top-level WriterAgent has tools and sub-agents."""
    agent = create_writer_agent()
    assert agent.name == "WriterAgent"
    assert writer_reviewer_loop in agent.sub_agents
    tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
    assert "export_bibtex" in tool_names
    assert "export_latex" in tool_names
    assert "export_citation_graph" in tool_names


def test_planner_agent_configuration():
    """Test PlannerAgent is properly instantiated with outline tools."""
    agent = create_planner_agent()
    assert agent.name == "PlannerAgent"
    tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
    assert "get_project_summary" in tool_names
    assert "get_ranked_papers" in tool_names
    assert "generate_outline" in tool_names


# ============================================================================
# Planning Tools Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_project_summary_tool():
    """Test get_project_summary tool calls planning_service."""
    mock_service = AsyncMock()
    mock_service.get_project_summary.return_value = {
        "project_id": "proj-123",
        "paper_count": 15,
        "question_count": 3,
        "gap_count": 1,
        "has_outline": True,
        "has_drafts": False,
        "questions": ["How do graph transformers scale?"],
    }

    ctx = DummyToolContext(state={"project_id": "proj-123"})

    with patch.object(ServiceRegistry, "planning_service", mock_service):
        res = await get_project_summary(ctx)  # type: ignore[arg-type]

    assert res["paper_count"] == 15
    assert res["question_count"] == 3
    assert len(res["questions"]) == 1


@pytest.mark.asyncio
async def test_generate_outline_tool_updates_state():
    """Test generate_outline calls planning service and sets tool_context.state['outline']."""
    mock_service = AsyncMock()
    mock_service.generate_outline.return_value = {
        "sections": [
            {
                "title": "Introduction",
                "description": "Background on graph transformers",
                "assigned_papers": ["10.1000/1"],
                "theme": "foundation",
            }
        ],
        "narrative_arc": "Foundations to applications",
        "style": "thematic",
        "saved_path": "/tmp/outlines/outline.json",
    }

    ctx = DummyToolContext(state={"project_id": "proj-123"})

    with patch.object(ServiceRegistry, "planning_service", mock_service):
        res = await generate_outline(style="thematic", tool_context=ctx)  # type: ignore[arg-type]

    assert "sections" in res
    assert "outline" in ctx.state
    assert len(ctx.state["outline"]["sections"]) == 1
    assert ctx.state["outline"]["narrative_arc"] == "Foundations to applications"
