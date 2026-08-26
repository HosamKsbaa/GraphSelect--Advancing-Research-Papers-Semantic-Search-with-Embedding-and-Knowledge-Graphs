"""Unit and integration tests for EvidenceSynthesizerAgent and literature comparison matrices (Milestone 2 / R2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.evidence_synthesizer import (
    create_evidence_synthesizer_agent,
    evidence_synthesizer_agent,
)
from agents.research.models import (
    ComparisonDimension,
    PaperFinding,
    StructuredComparisonMatrix,
)
from agents.research.tools.analysis_tools import (
    extract_paper_findings,
    generate_comparison_matrix,
    synthesize_evidence,
)
from core.llm.models import CompletionResponse, TokenUsage


@pytest.fixture
def mock_tool_context() -> ToolContext:
    """Mock ToolContext with project_id and state dict."""
    ctx = MagicMock(spec=ToolContext)
    ctx.state = {"project_id": "proj-synth-101"}
    return ctx


def test_evidence_synthesizer_agent_creation() -> None:
    """Test EvidenceSynthesizerAgent creates an LlmAgent with expected tools and instructions."""
    agent = create_evidence_synthesizer_agent()
    assert isinstance(agent, LlmAgent)
    assert agent.name == "EvidenceSynthesizerAgent"
    assert "Evidence Synthesizer Agent" in agent.instruction
    assert "extract_paper_findings" in agent.instruction
    assert "generate_comparison_matrix" in agent.instruction

    tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
    assert "extract_paper_findings" in tool_names
    assert "generate_comparison_matrix" in tool_names
    assert "synthesize_evidence" in tool_names
    assert "get_project_papers" in tool_names


def test_paper_finding_model_validation() -> None:
    """Test PaperFinding Pydantic model validation and serialization."""
    finding = PaperFinding(
        doi="10.1145/3292500.3330919",
        title="Graph Attention Networks",
        year=2018,
        methodology="Self-attention mechanisms over node neighborhoods",
        key_findings=[
            "Outperforms GCN on Cora, Citeseer, and Pubmed benchmarks",
            "Enables anisotropic message passing across edges",
        ],
        datasets_or_benchmarks=["Cora", "Citeseer", "Pubmed", "PPI"],
        limitations=["Higher computational complexity with multi-head attention"],
    )

    data = finding.model_dump()
    assert data["doi"] == "10.1145/3292500.3330919"
    assert data["year"] == 2018
    assert len(data["key_findings"]) == 2
    assert len(data["datasets_or_benchmarks"]) == 4
    assert len(data["limitations"]) == 1


def test_comparison_dimension_model_validation() -> None:
    """Test ComparisonDimension model with consensus and divergence fields."""
    dim = ComparisonDimension(
        dimension_name="Scalability & Depth",
        findings_by_doi={
            "10.1000/gcn": "Suffers from over-smoothing beyond 3-4 layers.",
            "10.1000/graphormer": "Maintains representation quality up to 12 layers using spatial encodings.",
        },
        consensus="Shallow message passing is effective for local graph homophily.",
        divergence="Transformers scale to deeper architectures than standard message-passing GNNs.",
    )

    assert dim.dimension_name == "Scalability & Depth"
    assert len(dim.findings_by_doi) == 2
    assert "over-smoothing" in dim.findings_by_doi["10.1000/gcn"]
    assert "Transformers scale" in dim.divergence


def test_structured_comparison_matrix_markdown_rendering() -> None:
    """Test rendering StructuredComparisonMatrix into a Markdown table."""
    dim1 = ComparisonDimension(
        dimension_name="Expressive Power",
        findings_by_doi={
            "10.1000/p1": "Bounded by 1-WL test",
            "10.1000/p2": "Matches 3-WL test with subgraph aggregations",
        },
        consensus="Standard message passing has expressive capacity bounds.",
        divergence="Higher-order architectures trade off speed for higher expressive power.",
    )
    dim2 = ComparisonDimension(
        dimension_name="Computational Cost",
        findings_by_doi={
            "10.1000/p1": "O(|V| + |E|)",
            "10.1000/p2": "O(|V|^2)",
        },
        consensus="Linear scaling is necessary for billion-scale graphs.",
        divergence="Quadratic transformer attention limits web-scale graph deployment.",
    )

    matrix = StructuredComparisonMatrix(
        project_id="proj-101",
        research_questions=["How do GNNs handle expressivity vs efficiency?"],
        dimensions=[dim1, dim2],
        synthesis_narrative="Comparative analysis reveals a fundamental trade-off between expressive power and computational efficiency.",
    )

    md_table = matrix.to_markdown_table()
    assert "| Dimension |" in md_table
    assert "Expressive Power" in md_table
    assert "Computational Cost" in md_table
    assert "10.1000/p1" in md_table
    assert "10.1000/p2" in md_table
    assert "Bounded by 1-WL test" in md_table
    assert matrix.synthesis_narrative.startswith("Comparative analysis")


@pytest.mark.asyncio
async def test_extract_paper_findings_tool(mock_tool_context: ToolContext) -> None:
    """Test extract_paper_findings tool with mocked Neo4j and LLM."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value={
        "doi": "10.1000/gnn-paper",
        "title": "Scalable Graph Neural Networks",
        "year": 2024,
        "abstract": "We propose a linear-time graph attention model evaluated on OGB benchmarks.",
    })

    mock_llm = AsyncMock()
    llm_payload = {
        "methodology": "Linear attention mechanism with node sampling",
        "key_findings": ["Achieves 92.4% accuracy on ogbn-arxiv", "Reduces GPU memory by 60%"],
        "datasets_or_benchmarks": ["ogbn-arxiv", "ogbn-products"],
        "limitations": ["Requires precomputed graph partition matrices"],
    }
    mock_llm.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps(llm_payload),
        usage=TokenUsage(prompt_tokens=50, completion_tokens=100, total_tokens=150),
    ))

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_llm = getattr(ServiceRegistry, "_llm", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._llm = mock_llm
    ServiceRegistry._initialized = True

    try:
        res = await extract_paper_findings(
            dois=["10.1000/gnn-paper"],
            tool_context=mock_tool_context,
        )
        assert res["total_extracted"] == 1
        findings = res["findings"]
        assert findings[0]["doi"] == "10.1000/gnn-paper"
        assert findings[0]["methodology"] == "Linear attention mechanism with node sampling"
        assert "92.4% accuracy" in findings[0]["key_findings"][0]
        assert "ogbn-arxiv" in findings[0]["datasets_or_benchmarks"]
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        if old_llm is not None:
            ServiceRegistry._llm = old_llm
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_generate_comparison_matrix_tool(mock_tool_context: ToolContext) -> None:
    """Test generate_comparison_matrix tool populates comparison_matrix in tool_context.state."""
    mock_llm = AsyncMock()
    matrix_llm_json = {
        "dimensions": [
            {
                "dimension_name": "Attention Sparsity",
                "findings_by_doi": {
                    "10.1000/p1": "Dense global attention",
                    "10.1000/p2": "Sparse top-k neighborhood attention",
                },
                "consensus": "Attention mechanisms improve feature aggregation.",
                "divergence": "Sparse attention achieves 5x speedup over dense models.",
            }
        ],
        "synthesis_narrative": "Sparse attention allows scaling graph transformers without accuracy loss.",
    }
    mock_llm.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps(matrix_llm_json),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=150, total_tokens=250),
    ))

    old_llm = getattr(ServiceRegistry, "_llm", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._llm = mock_llm
    ServiceRegistry._initialized = True

    try:
        sample_findings = [
            {
                "doi": "10.1000/p1",
                "title": "Dense Graph Attention",
                "methodology": "Global Transformer",
                "key_findings": ["High accuracy on small graphs"],
            },
            {
                "doi": "10.1000/p2",
                "title": "Sparse Graph Attention",
                "methodology": "Top-k Sparsification",
                "key_findings": ["Fast on large graphs"],
            },
        ]

        result = await generate_comparison_matrix(
            findings=sample_findings,
            research_questions=["How does attention sparsity impact graph scaling?"],
            tool_context=mock_tool_context,
        )

        assert result["dimensions_count"] == 1
        assert "matrix" in result
        assert "markdown_table" in result
        assert "synthesis_narrative" in result

        # Verify tool_context.state updated
        assert "comparison_matrix" in mock_tool_context.state
        stored_matrix = mock_tool_context.state["comparison_matrix"]
        assert len(stored_matrix["dimensions"]) == 1
        assert stored_matrix["dimensions"][0]["dimension_name"] == "Attention Sparsity"
    finally:
        if old_llm is not None:
            ServiceRegistry._llm = old_llm
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_synthesize_evidence_tool(mock_tool_context: ToolContext) -> None:
    """Test synthesize_evidence runs end-to-end on project library."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers = AsyncMock(return_value=[
        {"doi": "10.1000/1", "title": "Paper 1", "year": 2023, "abstract": "Study on graph neural networks."},
        {"doi": "10.1000/2", "title": "Paper 2", "year": 2024, "abstract": "Study on graph transformers."},
    ])
    mock_neo4j.get_paper_by_doi = AsyncMock(side_effect=lambda doi: {
        "doi": doi,
        "title": f"Title {doi}",
        "year": 2024,
        "abstract": f"Abstract content for {doi}",
    })
    mock_neo4j.get_research_questions = AsyncMock(return_value=[
        {"question_id": "q1", "text": "What are the core differences between GNNs and GTs?"}
    ])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=[
        # 1. extract findings for paper 1
        CompletionResponse(
            text=json.dumps({
                "methodology": "Message passing GNN",
                "key_findings": ["Good on local structures"],
                "datasets_or_benchmarks": ["Cora"],
                "limitations": ["Over-smoothing"],
            }),
            usage=TokenUsage(prompt_tokens=20, completion_tokens=40, total_tokens=60),
        ),
        # 2. extract findings for paper 2
        CompletionResponse(
            text=json.dumps({
                "methodology": "Global Graph Transformer",
                "key_findings": ["Captures long-range dependencies"],
                "datasets_or_benchmarks": ["Peptides"],
                "limitations": ["High memory usage"],
            }),
            usage=TokenUsage(prompt_tokens=20, completion_tokens=40, total_tokens=60),
        ),
        # 3. generate comparison matrix
        CompletionResponse(
            text=json.dumps({
                "dimensions": [
                    {
                        "dimension_name": "Dependency Modeling",
                        "findings_by_doi": {
                            "10.1000/1": "Local neighbor aggregation",
                            "10.1000/2": "Global all-to-all attention",
                        },
                        "consensus": "Capturing node context is critical.",
                        "divergence": "GNNs focus locally while GTs model long-range interactions.",
                    }
                ],
                "synthesis_narrative": "A synthesis of graph modeling paradigms.",
            }),
            usage=TokenUsage(prompt_tokens=50, completion_tokens=100, total_tokens=150),
        ),
    ])

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_llm = getattr(ServiceRegistry, "_llm", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._llm = mock_llm
    ServiceRegistry._initialized = True

    try:
        res = await synthesize_evidence(tool_context=mock_tool_context)
        assert res["paper_count"] == 2
        assert len(res["findings"]) == 2
        assert "comparison_matrix" in res
        assert "markdown_table" in res
        assert mock_tool_context.state["comparison_matrix"]["dimensions"][0]["dimension_name"] == "Dependency Modeling"
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        if old_llm is not None:
            ServiceRegistry._llm = old_llm
        ServiceRegistry._initialized = old_init
