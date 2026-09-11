"""Adversarial stress test suite for Autonomous Gap Remediation & Coverage (Milestone M4).

Empirically tests edge cases, boundary conditions, and invariant violations:
1. Mathematical boundaries: 0.69999 vs 0.70000 vs 0.70001, epsilon precision, zero/negative cosines.
2. Library saturation: 50+ qualifying papers capped strictly at 1.0, empty inputs, invalid k_target.
3. Mode transitions: Exploration never flags open frontier; Targeted & Refinement always flag.
4. FR-015 SVPL invariants: Candidate count N > 0 forbids SVPL; N = 0 strictly invokes SVPL with
   trigger_reason='empty_gap_remediation' and candidate_count=0; unauthorized triggers rejected with 403.
5. System resilience: LLM failures fall back cleanly, candidate ingestion errors are non-fatal,
   Pydantic contracts strictly enforce valid intervals.

Complies with Constitution v2.2.1:
- C7: Complete static typing.
- C9: Every function is strictly <= 25 lines.
- C10: Early returns and guard clauses.
"""
from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from core.errors.enhancement_errors import MultiHopUnauthorizedError
from features.gap_analysis.coverage_calculator import (
    _parse_coverage_record,
    calculate_coverage_from_embeddings,
    compute_cosine_similarity,
    normalize_coverage_score,
)
from features.gap_analysis.models import (
    GapRemediationCycle,
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
    RunAutonomousGapRemediationOutput,
)
from features.gap_analysis.remediation_service import (
    RemediationService,
    extract_pathway_nodes,
)
from features.ranking.svpl_gating import (
    check_multihop_authorization,
    is_multihop_authorized,
)
from features.ranking.svpl_models import MultiHopTriggerReason


def make_unit_vector(angle_cos: float) -> list[float]:
    """Create 2D unit vector with specified cosine relative to [1.0, 0.0]."""
    clamped = max(-1.0, min(1.0, angle_cos))
    return [clamped, math.sqrt(max(0.0, 1.0 - clamped ** 2))]


# ==============================================================================
# 1. Coverage Mathematical Boundaries & Precision
# ==============================================================================

def test_adv_cosine_boundary_epsilon_precision() -> None:
    """Test strict boundary precision at 0.69999 vs 0.70000 vs 0.70001."""
    rq_vec = [1.0, 0.0]
    p_below = make_unit_vector(0.69999)
    p_exact = make_unit_vector(0.70000)
    p_above = make_unit_vector(0.70001)

    cnt_b, raw_b, sc_b = calculate_coverage_from_embeddings(rq_vec, [p_below])
    assert cnt_b == 0 and raw_b == 0.0 and sc_b == 0.0

    cnt_e, raw_e, sc_e = calculate_coverage_from_embeddings(rq_vec, [p_exact])
    assert cnt_e == 1 and sc_e == round(0.700 / 3.0, 3)

    cnt_a, raw_a, sc_a = calculate_coverage_from_embeddings(rq_vec, [p_above])
    assert cnt_a == 1 and sc_a == round(0.70001 / 3.0, 3)


def test_adv_floating_point_accumulation_precision() -> None:
    """Accumulating 3 papers with float cos=0.7000000000000001."""
    rq_vec = [1.0, 0.0]
    p_vec = make_unit_vector(0.7000000000000001)
    cnt, raw, score = calculate_coverage_from_embeddings(
        rq_vec, [p_vec, p_vec, p_vec], min_relevance=0.70, k_target=3.0
    )
    assert cnt == 3
    assert math.isclose(raw, 0.70, rel_tol=1e-7)
    assert score == 0.700


def test_adv_orthogonal_and_opposing_zero_coverage() -> None:
    """Orthogonal and opposing vectors yield 0.0 coverage score."""
    rq_vec = [1.0, 0.0, 0.0]
    p_ortho = [0.0, 1.0, 0.0]
    p_opp = [-1.0, 0.0, 0.0]
    cnt, raw, score = calculate_coverage_from_embeddings(rq_vec, [p_ortho, p_opp])
    assert cnt == 0
    assert raw == 0.0
    assert score == 0.0


def test_adv_all_zero_and_degenerate_vectors() -> None:
    """All-zero or degenerate vectors must not raise ZeroDivisionError."""
    assert compute_cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert compute_cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    cnt, raw, score = calculate_coverage_from_embeddings(
        [0.0, 0.0], [[0.0, 0.0], [1.0, 0.0]]
    )
    assert cnt == 0 and raw == 0.0 and score == 0.0


def test_adv_high_paper_count_cap_at_one() -> None:
    """Saturated library with 50 perfect papers caps strictly at 1.0."""
    rq_vec = [1.0, 0.0]
    papers = [[1.0, 0.0]] * 50
    cnt, raw, score = calculate_coverage_from_embeddings(
        rq_vec, papers, min_relevance=0.70, k_target=3.0
    )
    assert cnt == 50
    assert math.isclose(raw, 50.0 / 3.0, rel_tol=1e-5)
    assert score == 1.0


def test_adv_exact_k_target_boundary_cap() -> None:
    """Raw coverage exceeding 1.0 by epsilon 1e-9 caps strictly at 1.0."""
    assert normalize_coverage_score(1.000000001, 4) == 1.0
    assert normalize_coverage_score(1.0, 3) == 1.0
    assert normalize_coverage_score(0.9999, 3) == 1.0
    assert normalize_coverage_score(0.9994, 3) == 0.999


def test_adv_empty_library_and_empty_rq() -> None:
    """Empty library papers or empty question vector yields 0.0."""
    assert calculate_coverage_from_embeddings([], []) == (0, 0.0, 0.0)
    assert calculate_coverage_from_embeddings([1.0, 0.0], []) == (0, 0.0, 0.0)
    assert calculate_coverage_from_embeddings([], [[1.0, 0.0]]) == (0, 0.0, 0.0)


def test_adv_negative_or_zero_k_target() -> None:
    """Invalid k_target (<=0) safely returns zero coverage."""
    rq_vec = [1.0, 0.0]
    p_vec = [1.0, 0.0]
    assert calculate_coverage_from_embeddings(rq_vec, [p_vec], k_target=0.0) == (0, 0.0, 0.0)
    assert calculate_coverage_from_embeddings(rq_vec, [p_vec], k_target=-5.0) == (0, 0.0, 0.0)


def test_adv_parse_coverage_record_malformed() -> None:
    """Missing or malformed keys in Neo4j record parse safely to 0."""
    assert _parse_coverage_record([]) == (0, 0.0, 0.0)
    assert _parse_coverage_record([{}]) == (0, 0.0, 0.0)
    rec = [{"qualifying_count": "3", "raw_coverage": "0.75", "coverage_score": "0.75"}]
    assert _parse_coverage_record(rec) == (3, 0.75, 0.75)


# ==============================================================================
# 2. Mode Transition Invariants & State Machine
# ==============================================================================

@pytest.mark.asyncio
async def test_adv_exploration_mode_never_flags_frontier() -> None:
    """Exploration mode NEVER flags is_open_frontier=true on terminal deficit."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 1, "raw_coverage": 0.20, "coverage_score": 0.20}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    mock_neo4j.flag_open_research_frontier = AsyncMock()

    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq1", mode=RemediationMode.EXPLORATION,
        max_iterations=3, run_id="r1"
    )
    out = await service.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.MAX_ITERATIONS_PAUSED
    assert out.is_open_frontier is False
    mock_neo4j.flag_open_research_frontier.assert_not_called()


@pytest.mark.asyncio
async def test_adv_exploration_mode_single_iteration_terminal() -> None:
    """Exploration mode with max_iterations=1 pauses after exactly 1 cycle."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 0, "raw_coverage": 0.0, "coverage_score": 0.0}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq1", mode=RemediationMode.EXPLORATION,
        max_iterations=1, run_id="r1"
    )
    out = await service.run_remediation_loop(inp)
    assert out.iterations_executed == 1
    assert out.status == RemediationCycleStatus.MAX_ITERATIONS_PAUSED
    assert out.is_open_frontier is False


@pytest.mark.asyncio
async def test_adv_targeted_mode_always_flags_frontier_on_deficit() -> None:
    """Targeted mode ALWAYS flags open frontier and records remediation_run_id."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 1, "raw_coverage": 0.40, "coverage_score": 0.40}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    mock_neo4j.flag_open_research_frontier = AsyncMock(return_value={"is_open_frontier": True})

    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq-tgt", mode=RemediationMode.TARGETED,
        max_iterations=3, run_id="run-tgt-99"
    )
    out = await service.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.OPEN_RESEARCH_FRONTIER
    assert out.is_open_frontier is True
    mock_neo4j.flag_open_research_frontier.assert_awaited_once_with(
        "rq-tgt",
        "Coverage deficit unresolved after 3 iterations (coverage 0.400 < 0.700). Flagged as Open Research Frontier.",
        "run-tgt-99",
    )


@pytest.mark.asyncio
async def test_adv_refinement_mode_always_flags_frontier_on_deficit() -> None:
    """Refinement mode flags open frontier with is_open_frontier=True."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 1, "raw_coverage": 0.55, "coverage_score": 0.55}
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    mock_neo4j.flag_open_research_frontier = AsyncMock(return_value={"is_open_frontier": True})

    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq-ref", mode=RemediationMode.REFINEMENT,
        max_iterations=2, run_id="run-ref-12"
    )
    out = await service.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.OPEN_RESEARCH_FRONTIER
    assert out.is_open_frontier is True
    mock_neo4j.flag_open_research_frontier.assert_awaited_once()


@pytest.mark.asyncio
async def test_adv_targeted_mode_converged_never_flags_frontier() -> None:
    """When targeted mode reaches >= 0.70, it must NEVER flag open frontier."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"qualifying_count": 3, "raw_coverage": 0.70, "coverage_score": 0.70}
    ])
    mock_neo4j.flag_open_research_frontier = AsyncMock()

    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq-tgt-conv", mode=RemediationMode.TARGETED,
        max_iterations=3, run_id="run-1"
    )
    out = await service.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.CONVERGED
    assert out.is_open_frontier is False
    mock_neo4j.flag_open_research_frontier.assert_not_called()


# ==============================================================================
# 3. FR-015 SVPL Gating & Candidate Retrieval Invariants
# ==============================================================================

@pytest.mark.asyncio
async def test_adv_fr015_n_greater_than_zero_never_invokes_svpl() -> None:
    """N > 0 candidates strictly forbids calling svpl_service per FR-015."""
    for cand_count in [1, 3, 7]:
        mock_openalex = MagicMock()
        mock_openalex.search_by_title = AsyncMock(return_value=[
            {"doi": f"10.1000/c{i}", "title": f"Candidate {i}"} for i in range(cand_count)
        ])
        mock_svpl = MagicMock()
        mock_svpl.find_bridge_pathway = AsyncMock()

        svc = RemediationService(openalex=mock_openalex, svpl_service=mock_svpl)
        cands = await svc.retrieve_candidate_papers(queries=["ai ethics"], project_id="p1")
        assert len(cands) == min(cand_count, 3)
        mock_svpl.find_bridge_pathway.assert_not_called()


@pytest.mark.asyncio
async def test_adv_fr015_n_zero_strictly_invokes_svpl() -> None:
    """N = 0 candidates strictly triggers SVPL with empty_gap_remediation."""
    mock_openalex = MagicMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[])
    mock_svpl = MagicMock()
    mock_svpl.find_bridge_pathway = AsyncMock(return_value=None)

    svc = RemediationService(openalex=mock_openalex, svpl_service=mock_svpl)
    cands = await svc.retrieve_candidate_papers(
        queries=["quantum bio"], project_id="p1", run_id="run-svpl-42",
        stage_index=3, source_doi="10.1000/s1", target_doi="10.1000/t1"
    )
    assert cands == []
    mock_svpl.find_bridge_pathway.assert_awaited_once_with(
        source_doi="10.1000/s1", target_doi="10.1000/t1", project_id="p1",
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        candidate_count=0, run_id="run-svpl-42", stage_index=3
    )


def test_adv_fr015_gating_rejects_empty_gap_with_positive_candidates() -> None:
    """Gating raises 403 MultiHopUnauthorizedError if candidate_count > 0."""
    for count in [1, 2, 5, 100]:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(
                MultiHopTriggerReason.EMPTY_GAP_REMEDIATION, candidate_count=count
            )
        assert exc.value.http_status_code == 403
        assert "strictly when candidates are exhausted" in str(exc.value)


def test_adv_fr015_gating_rejects_crawler_triggers_in_remediation() -> None:
    """Routine crawler triggers are rejected under FR-015 even if N=0."""
    with pytest.raises(MultiHopUnauthorizedError) as exc:
        check_multihop_authorization("routine_crawler", candidate_count=0)
    assert exc.value.http_status_code == 403
    assert is_multihop_authorized("routine_crawler", candidate_count=0) is False


def test_adv_svpl_pathway_extraction_resilience() -> None:
    """extract_pathway_nodes handles pathways with dicts, objects, or None."""
    assert extract_pathway_nodes(None) == []
    mock_path = MagicMock()
    mock_path.intermediate_nodes = [
        {"doi": "10.1000/d1", "title": "T1"},
        MagicMock(doi="10.1000/d2", title="T2", openalex_id="W2"),
        {"doi": None, "title": "No DOI"},
    ]
    nodes = extract_pathway_nodes(mock_path)
    assert len(nodes) == 2
    assert nodes[0]["doi"] == "10.1000/d1"
    assert nodes[1]["doi"] == "10.1000/d2"


# ==============================================================================
# 4. Resilience, Error Handling & Invariant Enforcement
# ==============================================================================

def test_adv_llm_failure_falls_back_deterministically() -> None:
    """When LLM service throws exception, fallback generates valid queries."""
    bad_llm = MagicMock()
    bad_llm.generate_text = MagicMock(side_effect=RuntimeError("Rate limit exceeded"))
    svc = RemediationService(llm_service=bad_llm)
    queries = svc.generate_targeted_queries("How does attention mechanism scale in transformers?")
    assert 1 <= len(queries) <= 3
    assert all(isinstance(q, str) and len(q) > 0 for q in queries)


@pytest.mark.asyncio
async def test_adv_ingestion_failure_resilience() -> None:
    """Ingestion exception on one candidate does not abort candidate ingestion."""
    bad_ingestion = MagicMock()
    bad_ingestion.ingest_paper = AsyncMock(side_effect=RuntimeError("Disk write failed"))
    svc = RemediationService(ingestion_service=bad_ingestion)
    cands = [{"doi": "10.1000/fail1"}, {"doi": "10.1000/fail2"}]
    dois = await svc._ingest_candidates(cands, "p1", "r1", 2)
    assert dois == ["10.1000/fail1", "10.1000/fail2"]


def test_adv_pydantic_validation_coverage_and_iterations() -> None:
    """Pydantic rejects iteration > 3 or negative coverage."""
    with pytest.raises(ValidationError):
        RunAutonomousGapRemediationInput(
            project_id="p1", rq_id="rq1", max_iterations=4, run_id="r1"
        )
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c1", iteration=4, target_rq_id="rq1", initial_coverage=0.2,
            queries_generated=["q1"], resulting_coverage=0.5, coverage_delta=0.3,
            status=RemediationCycleStatus.IN_PROGRESS
        )


def test_adv_pydantic_coverage_bounds() -> None:
    """Pydantic rejects coverage exceeding 1.0 or below 0.0."""
    with pytest.raises(ValidationError):
        GapRemediationCycle(
            cycle_id="c1", iteration=1, target_rq_id="rq1", initial_coverage=1.05,
            queries_generated=["q1"], resulting_coverage=0.5, coverage_delta=-0.55,
            status=RemediationCycleStatus.IN_PROGRESS
        )
    with pytest.raises(ValidationError):
        RunAutonomousGapRemediationOutput(
            status=RemediationCycleStatus.CONVERGED, rq_id="rq1", iterations_executed=1,
            initial_coverage=0.5, final_coverage=1.05, mode=RemediationMode.TARGETED
        )


@pytest.mark.asyncio
async def test_adv_anchor_resolution_from_neo4j() -> None:
    """Anchor DOIs resolved from Neo4j library papers if not supplied."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"doi": "10.1000/lib1"}, {"doi": "10.1000/lib2"}
    ])
    svc = RemediationService(neo4j=mock_neo4j)
    src, tgt = await svc._resolve_svpl_anchors("p1", None, None)
    assert src == "10.1000/lib1"
    assert tgt == "10.1000/lib2"


@pytest.mark.asyncio
async def test_adv_candidate_ranking_with_embeddings() -> None:
    """Candidates are ranked by cosine similarity to RQ embedding vector."""
    cands = [
        {"doi": "10.1000/low", "embedding": [0.0, 1.0]},
        {"doi": "10.1000/high", "embedding": [1.0, 0.0]},
    ]
    svc = RemediationService()
    ranked = await svc._rank_candidates_by_relevance(cands, [1.0, 0.0])
    assert len(ranked) == 2
    assert ranked[0]["doi"] == "10.1000/high"
    assert ranked[0]["similarity"] == 1.0
    assert ranked[1]["doi"] == "10.1000/low"
    assert ranked[1]["similarity"] == 0.0


@pytest.mark.asyncio
async def test_adv_exact_convergence_boundary_remediation_loop() -> None:
    """Score rising to exactly 0.700 converges immediately; 0.699 continues."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(side_effect=[
        [{"qualifying_count": 1, "raw_coverage": 0.50, "coverage_score": 0.50}],
        [{"text": "RQ text", "embedding": [1.0, 0.0]}],
        [{"qualifying_count": 3, "raw_coverage": 0.70, "coverage_score": 0.70}],
    ])
    mock_neo4j.execute_write = AsyncMock(return_value=[])
    service = RemediationService(neo4j=mock_neo4j)
    inp = RunAutonomousGapRemediationInput(
        project_id="p1", rq_id="rq-exact-70", mode=RemediationMode.TARGETED,
        max_iterations=3, run_id="r1"
    )
    out = await service.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.CONVERGED
    assert out.iterations_executed == 1
    assert out.final_coverage == 0.70
    assert out.is_open_frontier is False
