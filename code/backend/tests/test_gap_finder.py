"""Unit and integration tests for GapFinderAgent and literature gap analysis (Milestone 2 / R2)."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.gap_finder import create_gap_finder_agent
from agents.research.tools.analysis_tools import (
    analyze_coverage,
    compute_similarity,
    get_citation_stats,
    rank_papers,
    suggest_gap_queries,
)
from core.llm.models import CompletionResponse, TokenUsage


@pytest.fixture
def mock_tool_context() -> ToolContext:
    """Mock ToolContext with project_id and state dict."""
    ctx = MagicMock(spec=ToolContext)
    ctx.state = {"project_id": "proj-gap-101"}
    return ctx


def test_gap_finder_agent_creation() -> None:
    """Test GapFinderAgent creates an LlmAgent with expected tools and instructions."""
    agent = create_gap_finder_agent()
    assert isinstance(agent, LlmAgent)
    assert agent.name == "GapFinderAgent"
    assert "Gap Finder Agent" in agent.instruction
    assert "analyze_coverage" in agent.instruction
    assert "suggest_gap_queries" in agent.instruction
    assert "rank_papers" in agent.instruction

    tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
    assert "compute_similarity" in tool_names
    assert "get_citation_stats" in tool_names
    assert "analyze_coverage" in tool_names
    assert "suggest_gap_queries" in tool_names
    assert "rank_papers" in tool_names


@pytest.mark.asyncio
async def test_compute_similarity_tool(mock_tool_context: ToolContext) -> None:
    """Test compute_similarity tool with mock Neo4j."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions = AsyncMock(return_value=[
        {"question_id": "q1", "text": "Question 1"},
        {"question_id": "q2", "text": "Question 2"},
    ])
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/paper-sim", "question": "Question 1", "score": 0.90},
        {"doi": "10.1000/paper-sim", "question": "Question 2", "score": 0.70},
    ])

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        res = await compute_similarity(doi="10.1000/paper-sim", tool_context=mock_tool_context)
        assert res["doi"] == "10.1000/paper-sim"
        assert len(res["scores"]) == 2
        assert res["avg_score"] == 0.80
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_get_citation_stats_tool(mock_tool_context: ToolContext) -> None:
    """Test get_citation_stats tool returns aggregate citation and similarity stats."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers = AsyncMock(return_value=[
        {"doi": "10.1000/1", "cited_by_count": 40},
        {"doi": "10.1000/2", "cited_by_count": 60},
    ])
    mock_neo4j.get_research_questions = AsyncMock(return_value=["Q1", "Q2"])
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/1", "question": "Q1", "score": 0.85},
        {"doi": "10.1000/2", "question": "Q1", "score": 0.75},
        {"doi": "10.1000/1", "question": "Q2", "score": 0.95},
    ])

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        res = await get_citation_stats(tool_context=mock_tool_context)
        assert res["total_papers"] == 2
        assert res["total_citations"] == 100
        assert res["avg_citations"] == 50.0
        assert len(res["question_coverage"]) == 2
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_analyze_coverage_tool(mock_tool_context: ToolContext) -> None:
    """Test analyze_coverage classifies questions as covered or gaps based on similarity threshold."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions = AsyncMock(return_value=[
        {"question_id": "q1", "text": "Q1: Expressive Power"},
        {"question_id": "q2", "text": "Q2: Quantum Graphs"},
    ])
    mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1000/1"}])
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/1", "question": "Q1: Expressive Power", "score": 0.85},
        {"doi": "10.1000/1", "question": "Q2: Quantum Graphs", "score": 0.35},
    ])

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        res = await analyze_coverage(threshold=0.6, tool_context=mock_tool_context)
        assert res["total_questions"] == 2
        assert res["gap_count"] == 1
        assert len(res["covered_questions"]) == 1
        assert res["covered_questions"][0]["question"] == "Q1: Expressive Power"
        assert len(res["gap_questions"]) == 1
        assert res["gap_questions"][0]["question"] == "Q2: Quantum Graphs"
        assert res["overall_coverage"] == 0.5
        assert "Focus searches on:" in res["recommendation"]
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_suggest_gap_queries_tool(mock_tool_context: ToolContext) -> None:
    """Test suggest_gap_queries tool parses LLM response into query list."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps([
            "Quantum graph neural network algorithms",
            "Parameterized quantum circuits on graphs",
            "Quantum graph isomorphism tests",
        ]),
        usage=TokenUsage(prompt_tokens=30, completion_tokens=30, total_tokens=60),
    ))

    old_llm = getattr(ServiceRegistry, "_llm", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._llm = mock_llm
    ServiceRegistry._initialized = True

    try:
        res = await suggest_gap_queries(
            gap_question="How can quantum computing enhance graph representations?",
            max_queries=3,
            tool_context=mock_tool_context,
        )
        assert res["gap_question"] == "How can quantum computing enhance graph representations?"
        assert len(res["suggested_queries"]) == 3
        assert "Quantum graph neural network algorithms" in res["suggested_queries"]
    finally:
        if old_llm is not None:
            ServiceRegistry._llm = old_llm
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_rank_papers_tool(mock_tool_context: ToolContext) -> None:
    """Test rank_papers tool computes hybrid score combining similarity and PageRank."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers = AsyncMock(return_value=[
        {"doi": "10.1000/p1", "title": "Paper One", "year": 2021},
        {"doi": "10.1000/p2", "title": "Paper Two", "year": 2023},
    ])
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/p1", "score": 0.90},
        {"doi": "10.1000/p2", "score": 0.60},
    ])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={
        "10.1000/p1": 0.20,
        "10.1000/p2": 0.80,
    })

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        # weights: sim=0.7, pr=0.3
        # p1: 0.7 * 0.90 + 0.3 * 0.20 = 0.63 + 0.06 = 0.69
        # p2: 0.7 * 0.60 + 0.3 * 0.80 = 0.42 + 0.24 = 0.66
        res = await rank_papers(
            similarity_weight=0.7,
            pagerank_weight=0.3,
            tool_context=mock_tool_context,
        )
        assert res["total"] == 2
        ranked = res["ranked_papers"]
        assert ranked[0]["doi"] == "10.1000/p1"
        assert ranked[0]["hybrid_score"] == 0.69
        assert ranked[1]["doi"] == "10.1000/p2"
        assert ranked[1]["hybrid_score"] == 0.66
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_gap_finder_error_and_boundaries() -> None:
    """Test boundary cases: missing project_id in context and empty project graph."""
    res_no_ctx = await compute_similarity(doi="10.1000/test", tool_context=None)
    assert "error" in res_no_ctx

    res_no_state = await analyze_coverage(tool_context=MagicMock(state=None))
    assert "error" in res_no_state

    res_rank_no_ctx = await rank_papers(tool_context=None)
    assert "error" in res_rank_no_ctx
