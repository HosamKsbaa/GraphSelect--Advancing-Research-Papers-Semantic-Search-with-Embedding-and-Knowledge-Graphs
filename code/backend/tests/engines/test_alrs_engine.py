"""Contract and mathematical tests for `engines.alrs`.

Ported from archive commit 865cd08 (`tests/test_density_gated_pagerank.py`,
`tests/test_epistemic_graphselect.py`, and `tests/test_full_alrs_search_contracts.py`).
"""

from __future__ import annotations

import math
from uuid import uuid4

from engines.alrs import (
    ALRSSearchSettings,
    DiscoveryFrontierState,
    DiscoveryStartingPaper,
    SearchProfile,
    SimilarityObservation,
    adaptive_threshold,
    apply_researcher_epistemic_steering,
    calculate_candidate_subgraph_density,
    calculate_density_gate,
    calculate_density_gated_epistemic_rankings,
    calculate_density_gated_rankings,
    calculate_epistemic_pagerank,
    calculate_epistemic_rankings,
    calculate_rankings,
    citation_pagerank,
    compute_density_gated_weights,
    expansion_tasks,
    get_search_profile_metadata,
    normalize_search_profile,
    select_epistemic_frontier_task,
    select_fair_task,
)
from engines.jev import EpistemicDimensionScore, PaperEpistemicAssessment
from engines.openalex import OpenAlexWork
from engines.papers import CitationEdge


def make_assessment(
    doi: str,
    composite: float = 0.85,
    prune: bool = False,
    label: str = "include",
) -> PaperEpistemicAssessment:
    dim_align = EpistemicDimensionScore(
        dimension="alignment",
        selected_choice="direct_evidence",
        expected_utility=composite,
        normalized_entropy=0.1,
        confidence=0.9,
        discounted_score=composite,
        probabilities={"direct_evidence": 1.0},
    )
    dim_role = EpistemicDimensionScore(
        dimension="citation_role",
        selected_choice="foundational_or_extension",
        expected_utility=composite,
        normalized_entropy=0.1,
        confidence=0.9,
        discounted_score=composite,
        probabilities={"foundational_or_extension": 1.0},
    )
    dim_screen = EpistemicDimensionScore(
        dimension="screening",
        selected_choice=label,
        expected_utility=composite,
        normalized_entropy=0.1,
        confidence=0.9,
        discounted_score=composite,
        probabilities={label: 1.0},
    )
    return PaperEpistemicAssessment(
        doi=doi,
        alignment=dim_align,
        citation_role=dim_role,
        screening=dim_screen,
        composite_epistemic_score=composite,
        mean_entropy=0.1,
        mean_confidence=0.9,
        screening_label=label,  # type: ignore[arg-type]
        prune_subtree=prune,
        model="jev-1.13.0",
        input_hash="a" * 64,
    )


def test_citation_pagerank_sums_to_one_and_rewards_cited_nodes() -> None:
    dois = ["10.1000/a", "10.1000/b", "10.1000/c"]
    edges = [
        CitationEdge(source_doi="10.1000/a", target_doi="10.1000/c"),
        CitationEdge(source_doi="10.1000/b", target_doi="10.1000/c"),
    ]
    scores = citation_pagerank(dois, edges)
    assert abs(sum(scores.values()) - 1.0) < 1e-6
    assert scores["10.1000/c"] > scores["10.1000/a"]


def test_density_gate_zero_for_edgeless_graph_and_saturates_for_dense_graph() -> None:
    dois = ["10.1000/a", "10.1000/b", "10.1000/c"]
    assert calculate_candidate_subgraph_density(dois, []) == 0.0
    assert calculate_density_gate(0.0) == 0.0

    # Zero-edge graph reallocates 100% of PageRank weight to cosine similarity
    sim_w, pr_w = compute_density_gated_weights(base_similarity_weight=0.70, density=0.0)
    assert sim_w == 1.0 and pr_w == 0.0

    similarities = [
        SimilarityObservation(doi="10.1000/a", question="Q1", similarity_score=0.82),
        SimilarityObservation(doi="10.1000/b", question="Q1", similarity_score=0.45),
    ]
    ranked = calculate_density_gated_rankings(
        dois=dois[:2],
        edges=[],
        similarities=similarities,
        minimum_threshold=0.50,
        similarity_weight=0.70,
    )
    by_doi = {r.paper_key: r for r in ranked}
    assert abs((by_doi["10.1000/a"].hybrid_score or 0.0) - 0.82) < 1e-9
    assert by_doi["10.1000/a"].density_gated is True
    assert by_doi["10.1000/a"].subgraph_density == 0.0

    # Dense complete directed graph approaches full PageRank weight (0.30)
    dense_edges = [
        CitationEdge(source_doi="10.1000/a", target_doi="10.1000/b"),
        CitationEdge(source_doi="10.1000/b", target_doi="10.1000/c"),
        CitationEdge(source_doi="10.1000/a", target_doi="10.1000/c"),
    ]
    density = calculate_candidate_subgraph_density(dois, dense_edges)
    assert abs(density - 1.0) < 1e-9
    eff_sim, eff_pr = compute_density_gated_weights(0.70, density, steepness=20.0)
    assert abs(eff_sim + eff_pr - 1.0) < 1e-12
    assert abs(eff_pr - 0.30 * math.tanh(20.0)) < 1e-9


def test_epistemic_pagerank_and_rankings_suppress_pruned_subtrees() -> None:
    dois = ["10.1000/seed", "10.1000/good", "10.1000/hub_trap"]
    edges = [
        CitationEdge(source_doi="10.1000/seed", target_doi="10.1000/good"),
        CitationEdge(source_doi="10.1000/seed", target_doi="10.1000/hub_trap"),
    ]
    similarities = [
        SimilarityObservation(doi="10.1000/seed", question="Q1", similarity_score=0.90),
        SimilarityObservation(doi="10.1000/good", question="Q1", similarity_score=0.80),
        SimilarityObservation(doi="10.1000/hub_trap", question="Q1", similarity_score=0.75),
    ]
    assessments = {
        "10.1000/good": make_assessment("10.1000/good", composite=0.90, prune=False),
        "10.1000/hub_trap": make_assessment(
            "10.1000/hub_trap", composite=0.10, prune=True, label="exclude"
        ),
    }

    rankings = calculate_epistemic_rankings(
        dois=dois,
        edges=edges,
        similarities=similarities,
        minimum_threshold=0.50,
        similarity_weight=0.70,
        assessments=assessments,
        expanded_count=3,
    )
    by_doi = {r.paper_key: r for r in rankings}

    assert by_doi["10.1000/good"].can_expand is True
    assert by_doi["10.1000/hub_trap"].can_expand is False
    assert by_doi["10.1000/hub_trap"].jev_pruned is True
    assert by_doi["10.1000/hub_trap"].ucb_frontier_priority == 0.0
    assert (by_doi["10.1000/good"].epistemic_pagerank_score or 0.0) > (
        by_doi["10.1000/hub_trap"].epistemic_pagerank_score or 0.0
    )

    # Researcher steering can boost a gem or suppress a hub and cleanly restore
    steered = apply_researcher_epistemic_steering(
        rankings,
        edges,
        {"10.1000/good": "suppress_hub"},
    )
    steered_map = {r.paper_key: r for r in steered}
    assert steered_map["10.1000/good"].can_expand is False
    assert steered_map["10.1000/good"].epistemic_badge == "hub_trap_suppressed"

    restored = apply_researcher_epistemic_steering(steered, edges, {"10.1000/good": "neutral"})
    restored_map = {r.paper_key: r for r in restored}
    assert restored_map["10.1000/good"].can_expand is True
    assert restored_map["10.1000/good"].researcher_steering is None


def test_density_gated_epistemic_rankings_and_multi_frontier_scheduling() -> None:
    dois = ["10.1000/a", "10.1000/b"]
    similarities = [
        SimilarityObservation(doi="10.1000/a", question="Q1", similarity_score=0.80),
        SimilarityObservation(doi="10.1000/b", question="Q1", similarity_score=0.60),
    ]
    rankings = calculate_density_gated_epistemic_rankings(
        dois=dois,
        edges=[],
        similarities=similarities,
        minimum_threshold=0.50,
        similarity_weight=0.70,
    )
    assert all(r.density_gated for r in rankings)

    run_id = uuid4()
    roots = ["10.1000/a", "10.1000/b"]
    work_a = OpenAlexWork(
        id="https://openalex.org/W1",
        doi="10.1000/a",
        display_name="Paper A",
        referenced_works=["https://openalex.org/W10", "https://openalex.org/W11"],
    )
    work_b = OpenAlexWork(
        id="https://openalex.org/W2",
        doi="10.1000/b",
        display_name="Paper B",
        referenced_works=["https://openalex.org/W20"],
    )
    tasks = expansion_tasks(run_id, work_a, "10.1000/a", 1, roots) + expansion_tasks(
        run_id, work_b, "10.1000/b", 1, roots
    )
    state = DiscoveryFrontierState(
        run_id=run_id,
        starting_papers=[
            DiscoveryStartingPaper(doi="10.1000/a", title="Paper A"),
            DiscoveryStartingPaper(doi="10.1000/b", title="Paper B"),
        ],
        traversal_tasks=tasks,
    )
    first_task, _ = select_fair_task(state, eligible=set(roots))
    assert first_task is not None
    assert first_task.origin_doi == "10.1000/a"

    state.last_lane_index = first_task.lane_index
    second_task, _ = select_fair_task(state, eligible=set(roots))
    assert second_task is not None
    assert second_task.origin_doi == "10.1000/b"

    ucb_task, _ = select_epistemic_frontier_task(state, eligible=set(roots), rankings=rankings)
    assert ucb_task is not None
    assert ucb_task.parent_doi == "10.1000/a"


def test_settings_and_profile_aliases() -> None:
    assert (
        normalize_search_profile("content_expanded_rrf")
        == SearchProfile.CONTENT_ORIGINAL_EXPANDED_RRF
    )
    meta = get_search_profile_metadata("content_bm25")
    assert meta.id == SearchProfile.DEFAULT_BM25

    settings = ALRSSearchSettings(similarity_weight=0.65, density_gated_pagerank=True)
    assert abs(settings.pagerank_weight - 0.35) < 1e-9
    assert adaptive_threshold([], 0.4) == 0.4
    assert sum(calculate_epistemic_pagerank(["10.1000/a", "10.1000/b"], []).values()) > 0.99
    assert len(calculate_rankings(["10.1000/a"], [], [], 0.5, 0.7)) == 1
