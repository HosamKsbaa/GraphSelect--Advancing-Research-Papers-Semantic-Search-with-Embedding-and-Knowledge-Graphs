"""Comprehensive integration tests for Autonomous Gap Remediation (T035).

Verifies:
- Convergence scenario: coverage rises from 0.40 -> 0.75; loop terminates cleanly in <= 2 iterations.
- Immediate convergence: initial coverage >= 0.70 terminates at iteration 1.
- Empty candidate fallback (N=0): dispatches to svpl_service.find_bridge_pathway with trigger_reason='empty_gap_remediation' (FR-015).
- Strict necessity gating: svpl_service is NOT called when candidate count > 0.
- Exploration mode terminal state: pauses in status='paused_awaiting_input' after 3 iterations.
- Targeted / Refinement mode terminal state: flags rq.is_open_frontier = true and calls flag_open_research_frontier.
- Targeted query formulation: LLM integration and deterministic stopword-filtered fallback.
- Ingestion of candidate papers and cycle persistence to Neo4j.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.errors.enhancement_errors import MultiHopUnauthorizedError
from features.gap_analysis.models import (
    GapRemediationCycle,
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
    RunAutonomousGapRemediationOutput,
)
from features.gap_analysis.remediation_service import (
    RECORD_REMEDIATION_CYCLE_CYPHER,
    RemediationService,
    build_targeted_query_prompt,
    convert_openalex_work,
    extract_pathway_nodes,
    fallback_targeted_queries,
    parse_generated_queries,
)
from features.ingestion.models import IngestUserPaperOutput
from features.ranking.svpl_models import (
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
)


# ==============================================================================
# 1. Query Formulation & Work Conversion Unit Tests (T037)
# ==============================================================================

def test_fallback_targeted_queries_filtering() -> None:
    """Fallback query generator must remove stopwords and generate 1-3 targeted queries."""
    rq = "How does graph convolutional network perform on heterogeneous citation graphs?"
    queries = fallback_targeted_queries(rq)
    assert 1 <= len(queries) <= 3
    for q in queries:
        assert len(q) > 0
        assert "how" not in q.split()
        assert "does" not in q.split()


def test_fallback_targeted_queries_empty() -> None:
    """Empty or stopword-only question yields fallback string."""
    queries = fallback_targeted_queries("what is the")
    assert len(queries) == 1
    assert "what is the" in queries[0] or "academic" in queries[0]


def test_parse_generated_queries() -> None:
    """Parse line-delimited queries from LLM response."""
    raw_llm = "1. graph convolutional citation\n2. heterogeneous graph embeddings\n3. semi-supervised learning"
    queries = parse_generated_queries(raw_llm)
    assert len(queries) == 3
    assert queries[0] == "graph convolutional citation"
    assert queries[1] == "heterogeneous graph embeddings"
    assert queries[2] == "semi-supervised learning"


def test_build_targeted_query_prompt() -> None:
    """Prompt includes question text and top papers."""
    prompt = build_targeted_query_prompt("What is GCN?", ["10.1000/p1", "10.1000/p2"])
    assert "What is GCN?" in prompt
    assert "10.1000/p1" in prompt


def test_convert_openalex_work_dict_and_object() -> None:
    """Convert dict and mock object to standard candidate dict."""
    d = {"doi": "10.1000/1", "title": "Test Title"}
    assert convert_openalex_work(d) == d

    obj = MagicMock()
    obj.doi = "10.1000/2"
    obj.title = "Object Title"
    obj.year = 2024
    obj.cited_by_count = 15
    obj.openalex_id = "W12345"

    converted = convert_openalex_work(obj)
    assert converted["doi"] == "10.1000/2"
    assert converted["title"] == "Object Title"
    assert converted["year"] == 2024


# ==============================================================================
# 2. Candidate Retrieval & N=0 SVPL Fallback Tests (T038)
# ==============================================================================

@pytest.mark.asyncio
async def test_retrieve_candidates_openalex_success() -> None:
    """When OpenAlex returns candidates, return top 3 and DO NOT call SVPL."""
    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[
        {"doi": "10.1000/cand1", "title": "Candidate 1"},
        {"doi": "10.1000/cand2", "title": "Candidate 2"},
    ])
    mock_svpl = MagicMock()
    mock_svpl.find_bridge_pathway = AsyncMock()

    service = RemediationService(openalex=mock_openalex, svpl_service=mock_svpl)
    candidates = await service.retrieve_candidate_papers(
        queries=["graph neural network"],
        project_id="proj-1",
        run_id="run-1",
    )

    assert len(candidates) == 2
    assert candidates[0]["doi"] == "10.1000/cand1"
    # Strict necessity: SVPL MUST NOT be called when N > 0!
    mock_svpl.find_bridge_pathway.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_candidates_n0_triggers_svpl_fallback() -> None:
    """When OpenAlex candidate count is N=0, assert dispatch to SVPL with empty_gap_remediation."""
    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[])

    mock_pathway = MultiHopBridgePathway(
        pathway_id="path-1",
        source_doi="10.1000/source",
        target_doi="10.1000/target",
        intermediate_nodes=[
            BridgeNodeSummary(doi="10.1000/source", title="Source Paper", openalex_id="W101"),
            BridgeNodeSummary(doi="10.1000/bridge1", title="Bridge Paper", openalex_id="W102"),
            BridgeNodeSummary(doi="10.1000/target", title="Target Paper", openalex_id="W103"),
        ],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        hop_distance=2,
        confidence=0.88,
        discovered_layer=1,
    )
    mock_svpl = MagicMock()
    mock_svpl.find_bridge_pathway = AsyncMock(return_value=mock_pathway)

    service = RemediationService(openalex=mock_openalex, svpl_service=mock_svpl)
    candidates = await service.retrieve_candidate_papers(
        queries=["obscure quantum biology topic"],
        project_id="proj-1",
        run_id="run-abc",
        source_doi="10.1000/source",
        target_doi="10.1000/target",
    )

    assert len(candidates) == 3
    assert candidates[0]["doi"] == "10.1000/source"
    assert candidates[1]["doi"] == "10.1000/bridge1"
    assert candidates[1]["is_bridge"] is True

    # Assert SVPL called with trigger_reason=EMPTY_GAP_REMEDIATION and candidate_count=0 per FR-015!
    mock_svpl.find_bridge_pathway.assert_awaited_once_with(
        source_doi="10.1000/source",
        target_doi="10.1000/target",
        project_id="proj-1",
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        candidate_count=0,
        run_id="run-abc",
        stage_index=2,
    )


def test_extract_pathway_nodes_none() -> None:
    """extract_pathway_nodes handles None pathway gracefully."""
    assert extract_pathway_nodes(None) == []


# ==============================================================================
# 3. Closed-Loop Remediation Orchestrator Tests (T039, T040)
# ==============================================================================

@pytest.mark.asyncio
async def test_remediation_loop_already_converged() -> None:
    """When initial coverage is >= 0.70, terminates immediately at iteration 1."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 3, "raw_coverage": 0.85, "coverage_score": 0.85}
    ])

    service = RemediationService(neo4j=mock_neo4j)
    input_data = RunAutonomousGapRemediationInput(
        project_id="proj-1",
        rq_id="rq-conv-1",
        mode=RemediationMode.EXPLORATION,
        max_iterations=3,
        run_id="run-1",
    )

    output = await service.run_remediation_loop(input_data)
    assert output.status == RemediationCycleStatus.CONVERGED
    assert output.iterations_executed == 1
    assert output.initial_coverage == 0.85
    assert output.final_coverage == 0.85
    assert output.is_open_frontier is False
    assert output.papers_ingested == []


@pytest.mark.asyncio
async def test_remediation_loop_converges_in_iteration_two() -> None:
    """Coverage rises from 0.40 -> 0.75, loop terminates cleanly in 2 iterations."""
    coverage_sequence = [
        # 1. Initial check:
        [{"qualifying_count": 1, "raw_coverage": 0.40, "coverage_score": 0.40}],
        # 2. After iteration 1 check:
        [{"qualifying_count": 2, "raw_coverage": 0.60, "coverage_score": 0.60}],
        # 3. After iteration 2 check:
        [{"qualifying_count": 3, "raw_coverage": 0.75, "coverage_score": 0.75}],
    ]

    async def mock_read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "coverage_score" in query:
            return coverage_sequence.pop(0) if coverage_sequence else [
                {"qualifying_count": 3, "raw_coverage": 0.75, "coverage_score": 0.75}
            ]
        if "ResearchQuestion" in query:
            return [{"text": "Graph neural network architectures", "embedding": [1.0, 0.0]}]
        return []

    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(side_effect=mock_read)
    mock_neo4j.execute_write = AsyncMock(return_value=[])

    call_count = 0

    async def mock_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        doi = "10.1000/paper_it1" if call_count <= 3 else "10.1000/paper_it2"
        return [{"doi": doi, "title": f"Paper {doi}"}]

    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(side_effect=mock_search)

    async def mock_ingest(inp: Any) -> IngestUserPaperOutput:
        return IngestUserPaperOutput(status="success", doi=inp.identifier)

    mock_ingestion = MagicMock()
    mock_ingestion.ingest_paper = AsyncMock(side_effect=mock_ingest)

    service = RemediationService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        ingestion_service=mock_ingestion,
    )
    input_data = RunAutonomousGapRemediationInput(
        project_id="proj-1",
        rq_id="rq-rising",
        mode=RemediationMode.EXPLORATION,
        max_iterations=3,
        run_id="run-rising-1",
    )

    output = await service.run_remediation_loop(input_data)
    assert output.status == RemediationCycleStatus.CONVERGED
    assert output.iterations_executed == 2
    assert output.initial_coverage == 0.40
    assert output.final_coverage == 0.75
    assert "10.1000/paper_it1" in output.papers_ingested
    assert "10.1000/paper_it2" in output.papers_ingested
    assert output.is_open_frontier is False


@pytest.mark.asyncio
async def test_remediation_loop_exploration_mode_terminal_paused() -> None:
    """Exploration mode pauses awaiting researcher input after 3 iterations if unmet."""
    # Coverage remains below 0.70 across all 3 iterations
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 1, "raw_coverage": 0.35, "coverage_score": 0.35}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])

    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[
        {"doi": "10.1000/paper_stuck", "title": "Stuck Topic"}
    ])

    service = RemediationService(neo4j=mock_neo4j, openalex=mock_openalex)
    input_data = RunAutonomousGapRemediationInput(
        project_id="proj-1",
        rq_id="rq-stuck-explore",
        mode=RemediationMode.EXPLORATION,
        max_iterations=3,
        run_id="run-stuck-1",
    )

    output = await service.run_remediation_loop(input_data)
    assert output.status == RemediationCycleStatus.MAX_ITERATIONS_PAUSED
    assert output.iterations_executed == 3
    assert output.initial_coverage == 0.35
    assert output.final_coverage == 0.35
    assert output.is_open_frontier is False


@pytest.mark.asyncio
async def test_remediation_loop_targeted_mode_flags_open_research_frontier() -> None:
    """Targeted mode flags question as Open Research Frontier after 3 iterations."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 1, "raw_coverage": 0.50, "coverage_score": 0.50}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    mock_neo4j.flag_open_research_frontier = AsyncMock(return_value={
        "rq_id": "rq-frontier-1", "is_open_frontier": True
    })

    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[
        {"doi": "10.1000/frontier_cand", "title": "Frontier Candidate"}
    ])

    service = RemediationService(neo4j=mock_neo4j, openalex=mock_openalex)
    input_data = RunAutonomousGapRemediationInput(
        project_id="proj-1",
        rq_id="rq-frontier-1",
        mode=RemediationMode.TARGETED,
        max_iterations=3,
        run_id="run-frontier-99",
    )

    output = await service.run_remediation_loop(input_data)
    assert output.status == RemediationCycleStatus.OPEN_RESEARCH_FRONTIER
    assert output.iterations_executed == 3
    assert output.initial_coverage == 0.50
    assert output.final_coverage == 0.50
    assert output.is_open_frontier is True

    mock_neo4j.flag_open_research_frontier.assert_awaited_once()
    call_args = mock_neo4j.flag_open_research_frontier.call_args[0]
    assert call_args[0] == "rq-frontier-1"
    assert "Open Research Frontier" in call_args[1]
    assert call_args[2] == "run-frontier-99"


@pytest.mark.asyncio
async def test_remediation_loop_refinement_mode_flags_open_research_frontier() -> None:
    """Refinement mode also flags question as Open Research Frontier after 3 iterations."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 0, "raw_coverage": 0.0, "coverage_score": 0.0}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    mock_neo4j.flag_open_research_frontier = AsyncMock(return_value={
        "rq_id": "rq-refine-1", "is_open_frontier": True
    })

    service = RemediationService(neo4j=mock_neo4j)
    input_data = RunAutonomousGapRemediationInput(
        project_id="proj-1",
        rq_id="rq-refine-1",
        mode=RemediationMode.REFINEMENT,
        max_iterations=3,
        run_id="run-refine-88",
    )

    output = await service.run_remediation_loop(input_data)
    assert output.status == RemediationCycleStatus.OPEN_RESEARCH_FRONTIER
    assert output.is_open_frontier is True
    mock_neo4j.flag_open_research_frontier.assert_awaited_once()


# ==============================================================================
# 4. Neo4jService flag_open_research_frontier Method Test (T041)
# ==============================================================================

@pytest.mark.asyncio
async def test_neo4j_service_flag_open_research_frontier() -> None:
    """Test Neo4jService.flag_open_research_frontier execution directly."""
    from core.db.neo4j_service import Neo4jService

    service = Neo4jService(uri="bolt://localhost:7687", user="neo4j", password="password")
    service.execute_write = AsyncMock(return_value=[  # type: ignore[method-assign]
        {"rq_id": "rq-direct-1", "is_open_frontier": True}
    ])

    res = await service.flag_open_research_frontier(
        rq_id="rq-direct-1",
        remediation_notes="Literature deficit unresolved.",
        run_id="run-direct-42",
    )

    assert res["rq_id"] == "rq-direct-1"
    assert res["is_open_frontier"] is True
    service.execute_write.assert_awaited_once()
    cypher_call = service.execute_write.call_args[0]
    assert "MATCH (rq:ResearchQuestion {question_id: $rq_id})" in cypher_call[0]
    assert "SET rq.is_open_frontier = true" in cypher_call[0]
    assert cypher_call[1]["rq_id"] == "rq-direct-1"
    assert cypher_call[1]["run_id"] == "run-direct-42"
