"""Unit and integration tests for Autonomous Candidate Appraisal & Strategic Recommendations (Milestone 2).

Tests candidate pool partitioning across the 3 archetypes:
  1. Foundational Prior Art (high backward references, mature citations, age >= 3 years)
  2. Contemporary Breakthroughs (high cosine similarity >= 0.60, recent year 2024-2026)
  3. Topological Bridges (high graph PageRank, in-graph degree, balanced multi-RQ similarity)
Tests score normalization, edge cases (zero citations, single item, empty pool),
evidence-grounded academic rationales, and the 4 structured steering options.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.tools.retrieval_tools import run_graphselect_traversal
from features.ranking.appraisal_service import appraise_1hop_candidate_pool
from features.ranking.models import (
    CandidatePaperState,
    SteeringActionOption,
    TraversalAppraisalResult,
)
from features.search.models import OneHopExpansionResult


@pytest.fixture
def mock_candidate_pool() -> list[CandidatePaperState]:
    """Create a diverse candidate pool of 6 papers representing all 3 archetypes."""
    return [
        # Foundational Prior Art: 2020 paper, 2500 citations, backward reference, high maturity
        CandidatePaperState(
            doi="10.1145/foundational.001",
            title="Spectral Graph Convolutions: Foundations and Complexity Bounds",
            authors=["Smith, Alice", "Jones, Bob"],
            year=2020,
            venue="ACM Computing Surveys",
            abstract_snippet="Theoretical survey on spectral graph convolution and message passing bounds.",
            direction="backward_reference",
            citation_count=2500,
            in_graph_degree=2,
            pagerank_score=0.03,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.72},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.45},
            ],
            max_similarity=0.72,
            mean_similarity=0.585,
            already_in_library=False,
            embedding_cached=True,
        ),
        # Contemporary Breakthrough 1: 2025 paper, high similarity (0.93), forward citation
        CandidatePaperState(
            doi="10.1016/contemporary.002",
            title="Asynchronous Mini-Batch Subgraph Sampling on Distributed GPUs",
            authors=["Zhang, Wei", "Kumar, Rajesh"],
            year=2025,
            venue="IEEE Transactions on Knowledge and Data Engineering",
            abstract_snippet="Demonstrates a 4.2x speedup in distributed GNN training via dynamic neighbor sampling.",
            direction="forward_citation",
            citation_count=35,
            in_graph_degree=1,
            pagerank_score=0.02,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.93},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.50},
            ],
            max_similarity=0.93,
            mean_similarity=0.715,
            already_in_library=False,
            embedding_cached=True,
        ),
        # Contemporary Breakthrough 2: 2026 paper, high similarity (0.88), forward citation
        CandidatePaperState(
            doi="10.1109/contemporary.003",
            title="Zero-Shot Over-smoothing Attenuation via Adaptive Residuals",
            authors=["Lee, Daniel", "Park, Soo"],
            year=2026,
            venue="ICLR 2026",
            abstract_snippet="Mitigates node representation collapse in deep 64-layer graph architectures.",
            direction="forward_citation",
            citation_count=12,
            in_graph_degree=1,
            pagerank_score=0.015,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.65},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.88},
            ],
            max_similarity=0.88,
            mean_similarity=0.765,
            already_in_library=False,
            embedding_cached=True,
        ),
        # Topological Bridge 1: High degree (6), high PageRank (0.12), highly balanced across both RQs
        CandidatePaperState(
            doi="10.1007/bridge.004",
            title="Unifying Graph Sparsification and Representation Homophily",
            authors=["Patel, Ravi", "Tan, Yuan"],
            year=2024,
            venue="Data Mining and Knowledge Discovery",
            abstract_snippet="High centrality connector establishing mathematical equivalence between sparse sampling and feature preservation.",
            direction="both",
            citation_count=180,
            in_graph_degree=6,
            pagerank_score=0.12,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.84},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.81},
            ],
            max_similarity=0.84,
            mean_similarity=0.825,
            already_in_library=False,
            embedding_cached=True,
        ),
        # Foundational Prior Art 2: 2018 paper, 6400 citations, backward reference
        CandidatePaperState(
            doi="10.1038/foundational.005",
            title="Deep Learning on Graphs: A Comprehensive Survey",
            authors=["Brown, Charles", "Taylor, David"],
            year=2018,
            venue="Nature Machine Intelligence",
            abstract_snippet="The classical comprehensive survey on graph neural network taxonomies and benchmarks.",
            direction="backward_reference",
            citation_count=6400,
            in_graph_degree=3,
            pagerank_score=0.04,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.68},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.60},
            ],
            max_similarity=0.68,
            mean_similarity=0.64,
            already_in_library=True,
            embedding_cached=True,
        ),
        # Topological Bridge 2: High in-graph degree (5), PageRank (0.09)
        CandidatePaperState(
            doi="10.1007/bridge.006",
            title="Multi-Scale Topology Preservation in Large Academic Networks",
            authors=["Garcia, Elena"],
            year=2023,
            venue="Journal of Complex Networks",
            abstract_snippet="Intermediary citation bridge analyzing multi-resolution network clustering.",
            direction="both",
            citation_count=95,
            in_graph_degree=5,
            pagerank_score=0.09,
            similarity_scores=[
                {"question_id": "rq-1", "question": "Scalability in GNNs", "score": 0.77},
                {"question_id": "rq-2", "question": "Over-smoothing mitigation", "score": 0.75},
            ],
            max_similarity=0.77,
            mean_similarity=0.76,
            already_in_library=False,
            embedding_cached=True,
        ),
    ]


def test_candidate_pool_partitioning_archetype_assignment(
    mock_candidate_pool: list[CandidatePaperState],
) -> None:
    """Verify that candidate papers are partitioned accurately into the 3 archetypes."""
    expansion_res = OneHopExpansionResult(
        seed_doi="10.1145/seed.paper",
        seed_title="Efficient Graph Representation Learning",
        cycle_level=1,
        total_discovered=len(mock_candidate_pool),
        total_new=5,
        forward_count=2,
        backward_count=2,
        both_count=2,
        candidates=mock_candidate_pool,
        new_dois=[c.doi for c in mock_candidate_pool],
        traversal_summary=["Completed 1-hop traversal."],
        errors=[],
    )

    appraisal: TraversalAppraisalResult = appraise_1hop_candidate_pool(
        expansion_res,
        current_year=2026,
    )

    assert isinstance(appraisal, TraversalAppraisalResult)
    assert appraisal.seed_doi == "10.1145/seed.paper"
    assert appraisal.total_discovered == 6

    # Verify Foundational Prior Art partition
    foundational_dois = [p.doi for p in appraisal.foundational_prior_art]
    assert "10.1038/foundational.005" in foundational_dois
    assert "10.1145/foundational.001" in foundational_dois

    # Verify Contemporary Breakthroughs partition
    contemporary_dois = [p.doi for p in appraisal.contemporary_breakthroughs]
    assert "10.1016/contemporary.002" in contemporary_dois
    assert "10.1109/contemporary.003" in contemporary_dois

    # Verify Topological Bridges partition
    bridge_dois = [p.doi for p in appraisal.topological_bridges]
    assert "10.1007/bridge.004" in bridge_dois


def test_evidence_grounded_academic_rationales(
    mock_candidate_pool: list[CandidatePaperState],
) -> None:
    """Verify generated academic rationales reference verifiable metadata, years, citations, and RQ scores."""
    expansion_res = OneHopExpansionResult(
        seed_doi="10.1145/seed.paper",
        seed_title="Efficient Graph Representation Learning",
        cycle_level=1,
        total_discovered=len(mock_candidate_pool),
        total_new=5,
        candidates=mock_candidate_pool,
    )

    appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

    # Check Foundational paper rationale
    foundational_p = appraisal.foundational_prior_art[0]
    assert foundational_p.recommendation_rationale != ""
    assert str(foundational_p.citation_count) in foundational_p.recommendation_rationale or f"{foundational_p.citation_count:,}" in foundational_p.recommendation_rationale
    assert str(foundational_p.year) in foundational_p.recommendation_rationale

    # Check Contemporary paper rationale
    contemporary_p = appraisal.contemporary_breakthroughs[0]
    assert contemporary_p.recommendation_rationale != ""
    assert str(contemporary_p.year) in contemporary_p.recommendation_rationale
    assert f"{contemporary_p.max_similarity:.2f}" in contemporary_p.recommendation_rationale

    # Check Bridge paper rationale
    bridge_p = appraisal.topological_bridges[0]
    assert bridge_p.recommendation_rationale != ""
    assert str(bridge_p.in_graph_degree) in bridge_p.recommendation_rationale
    assert f"{bridge_p.pagerank_score:.3f}" in bridge_p.recommendation_rationale


def test_formulate_four_steering_action_options(
    mock_candidate_pool: list[CandidatePaperState],
) -> None:
    """Verify formulation of 4 structured SteeringActionOption items (Foundational, Contemporary, Bridge, Adopt)."""
    expansion_res = OneHopExpansionResult(
        seed_doi="10.1145/seed.paper",
        seed_title="Seed Graph Representation",
        cycle_level=1,
        total_discovered=len(mock_candidate_pool),
        total_new=5,
        candidates=mock_candidate_pool,
    )

    appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)
    options = appraisal.steering_options

    assert len(options) == 4

    opt_a, opt_b, opt_c, opt_d = options[0], options[1], options[2], options[3]

    # Option A: Foundational Deep-Dive
    assert opt_a.option_id == "option_a_foundational"
    assert opt_a.action_type == "expand_deeper"
    assert opt_a.target_doi is not None
    assert "foundational" in opt_a.target_doi.lower() or opt_a.target_doi in [p.doi for p in appraisal.foundational_prior_art]
    assert "Foundational" in opt_a.label

    # Option B: Contemporary Deep-Dive
    assert opt_b.option_id == "option_b_contemporary"
    assert opt_b.action_type == "expand_deeper"
    assert opt_b.target_doi is not None
    assert "contemporary" in opt_b.target_doi.lower() or opt_b.target_doi in [p.doi for p in appraisal.contemporary_breakthroughs]
    assert "Contemporary" in opt_b.label

    # Option C: Bridge Deep-Dive
    assert opt_c.option_id == "option_c_bridge"
    assert opt_c.action_type == "expand_deeper"
    assert opt_c.target_doi is not None
    assert "bridge" in opt_c.target_doi.lower() or opt_c.target_doi in [p.doi for p in appraisal.topological_bridges]
    assert "Bridge" in opt_c.label

    # Option D: Adopt & Finalize
    assert opt_d.option_id == "option_d_adopt_finalize"
    assert opt_d.action_type == "add_to_library"
    assert opt_d.target_doi is None
    assert "Library" in opt_d.label or "Conclude" in opt_d.label


def test_empty_candidate_pool_handles_gracefully() -> None:
    """Verify empty candidate pool returns clean appraisal object with fallback option without raising exceptions."""
    expansion_res = OneHopExpansionResult(
        seed_doi="10.1000/isolated.paper",
        seed_title="Isolated Work",
        cycle_level=1,
        total_discovered=0,
        total_new=0,
        candidates=[],
    )

    appraisal = appraise_1hop_candidate_pool(expansion_res)

    assert appraisal.total_discovered == 0
    assert len(appraisal.foundational_prior_art) == 0
    assert len(appraisal.contemporary_breakthroughs) == 0
    assert len(appraisal.topological_bridges) == 0
    assert len(appraisal.steering_options) >= 1
    assert "No 1-hop candidate papers discovered" in appraisal.strategic_recommendation


def test_single_candidate_normalization_and_partitioning() -> None:
    """Verify single candidate paper executes mathematical score normalization safely."""
    single_cand = CandidatePaperState(
        doi="10.1000/only.one",
        title="Sole Foundational Work",
        year=2019,
        citation_count=100,
        in_graph_degree=1,
        pagerank_score=0.05,
        max_similarity=0.75,
        mean_similarity=0.75,
        direction="backward_reference",
    )

    expansion_res = OneHopExpansionResult(
        seed_doi="10.1000/seed",
        seed_title="Seed",
        cycle_level=1,
        total_discovered=1,
        total_new=1,
        candidates=[single_cand],
    )

    appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

    assert appraisal.total_discovered == 1
    assert len(appraisal.steering_options) == 4
    for opt in appraisal.steering_options[:3]:
        assert opt.target_doi == "10.1000/only.one"


def test_zero_citations_and_zero_pagerank_numerical_stability() -> None:
    """Verify candidate papers with zero citations and zero PageRank calculate scores stably without zero division."""
    zero_cand1 = CandidatePaperState(
        doi="10.1000/zero1",
        title="Zero Citation Paper 1",
        year=2025,
        citation_count=0,
        in_graph_degree=0,
        pagerank_score=0.0,
        max_similarity=0.85,
        mean_similarity=0.85,
        direction="forward_citation",
    )
    zero_cand2 = CandidatePaperState(
        doi="10.1000/zero2",
        title="Zero Citation Paper 2",
        year=2015,
        citation_count=0,
        in_graph_degree=0,
        pagerank_score=0.0,
        max_similarity=0.40,
        mean_similarity=0.40,
        direction="backward_reference",
    )

    expansion_res = OneHopExpansionResult(
        seed_doi="10.1000/seed",
        seed_title="Seed",
        cycle_level=1,
        total_discovered=2,
        total_new=2,
        candidates=[zero_cand1, zero_cand2],
    )

    appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

    assert appraisal.total_discovered == 2
    # Verify scores are valid finite floats
    for p in [zero_cand1, zero_cand2]:
        for score_val in p.archetype_scores.values():
            assert isinstance(score_val, float)
            assert not math.isnan(score_val)
            assert not math.isinf(score_val)


@pytest.mark.asyncio
async def test_run_graphselect_traversal_tool_returns_appraisal_payload() -> None:
    """Verify run_graphselect_traversal tool returns the rich appraisal payload alongside candidates."""
    mock_candidates = [
        CandidatePaperState(
            doi="10.1000/p1",
            title="Seminal Foundation",
            year=2020,
            citation_count=1500,
            direction="backward_reference",
            in_graph_degree=2,
            similarity_scores=[{"question_id": "rq-1", "score": 0.70}],
            max_similarity=0.70,
            mean_similarity=0.70,
        ),
        CandidatePaperState(
            doi="10.1000/p2",
            title="Recent Breakthrough",
            year=2025,
            citation_count=20,
            direction="forward_citation",
            in_graph_degree=1,
            similarity_scores=[{"question_id": "rq-1", "score": 0.92}],
            max_similarity=0.92,
            mean_similarity=0.92,
        ),
    ]

    mock_expansion = OneHopExpansionResult(
        seed_doi="10.1145/test.seed",
        seed_title="Seed Work",
        cycle_level=1,
        total_discovered=2,
        total_new=2,
        forward_count=1,
        backward_count=1,
        both_count=0,
        candidates=mock_candidates,
        new_dois=["10.1000/p1", "10.1000/p2"],
        traversal_summary=["Completed 1-hop traversal."],
        errors=[],
    )

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion.return_value = mock_expansion

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {"project_id": "proj-999"}

    old_crawler = getattr(ServiceRegistry, "_crawler_service", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._crawler_service = mock_crawler
    ServiceRegistry._initialized = True

    try:
        res = await run_graphselect_traversal(
            seed_doi="10.1145/test.seed",
            max_depth=1,
            tool_context=mock_ctx,
        )

        assert res["status"] == "completed"
        assert "appraisal" in res
        assert "foundational_prior_art" in res
        assert "contemporary_breakthroughs" in res
        assert "topological_bridges" in res
        assert "strategic_recommendation" in res
        assert "steering_options" in res
        assert len(res["steering_options"]) == 4
    finally:
        if old_crawler is not None:
            ServiceRegistry._crawler_service = old_crawler
        ServiceRegistry._initialized = old_init
