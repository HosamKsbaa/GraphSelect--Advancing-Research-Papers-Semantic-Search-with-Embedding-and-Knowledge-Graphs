"""Epistemically-Biased PageRank (E-PR) and Upper-Confidence-Bound (E-UCB) Frontier Ranking.

Ported from archive commit 865cd08 (`code/backend/alrs_tool/search/epistemic_pagerank.py`).
"""

from __future__ import annotations

import math

from engines.jev import PaperEpistemicAssessment, compute_bridge_scores_by_doi
from engines.papers import CitationEdge, identity_from_key

from .ranking import (
    DEFAULT_DENSITY_STEEPNESS,
    EMBEDDING_VERSION,
    PaperRanking,
    RankingBeforeSteering,
    SimilarityObservation,
    adaptive_threshold,
    calculate_candidate_subgraph_density,
    calculate_density_gate,
    citation_pagerank,
    compute_density_gated_weights,
)

PRIOR_FLOOR = 1e-4
DAMPING_FACTOR = 0.85


def calculate_node_epistemic_potentials(
    nodes: list[str],
    best_similarities: dict[str, SimilarityObservation],
    assessments: dict[str, PaperEpistemicAssessment],
    similarity_potential_weight: float = 0.50,
) -> dict[str, float]:
    """Compute node potential Phi(u) combining semantic similarity and Jev epistemic utility."""
    potentials: dict[str, float] = {}
    for doi in nodes:
        assessment = assessments.get(doi)
        if assessment is not None and assessment.prune_subtree:
            potentials[doi] = PRIOR_FLOOR
            continue
        observation = best_similarities.get(doi)
        clamped_sim = max(0.0, observation.similarity_score) if observation is not None else 0.0
        if assessment is not None:
            combined = (
                similarity_potential_weight * clamped_sim
                + (1.0 - similarity_potential_weight) * assessment.composite_epistemic_score
            )
            potentials[doi] = max(PRIOR_FLOOR, combined)
        elif observation is not None:
            potentials[doi] = max(PRIOR_FLOOR, clamped_sim)
        else:
            potentials[doi] = PRIOR_FLOOR
    return potentials


def build_weighted_outgoing_transitions(
    nodes: list[str],
    edges: list[CitationEdge],
    potentials: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Weight outgoing citation transitions W(v -> u) proportionally to target potential Phi(u)."""
    outgoing_targets: dict[str, set[str]] = {doi: set() for doi in nodes}
    for edge in edges:
        if edge.source_key in outgoing_targets and edge.target_key in outgoing_targets:
            outgoing_targets[edge.source_key].add(edge.target_key)
    transitions: dict[str, dict[str, float]] = {}
    for source, targets in outgoing_targets.items():
        if not targets:
            transitions[source] = {}
            continue
        total_weight = sum(potentials[target] for target in targets)
        transitions[source] = {
            target: potentials[target] / total_weight for target in sorted(targets)
        }
    return transitions


def calculate_epistemic_pagerank(
    dois: list[str],
    edges: list[CitationEdge],
    potentials: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute Epistemically-Biased PageRank (E-PR) over the local citation subgraph."""
    nodes = sorted(set(dois))
    if not nodes:
        return {}
    node_potentials = {doi: max(PRIOR_FLOOR, (potentials or {}).get(doi, 1.0)) for doi in nodes}
    total_potential = sum(node_potentials.values())
    teleport = {doi: node_potentials[doi] / total_potential for doi in nodes}
    transitions = build_weighted_outgoing_transitions(nodes, edges, node_potentials)
    scores = dict(teleport)
    for _ in range(200):
        dangling_mass = sum(scores[doi] for doi in nodes if not transitions[doi])
        base_factor = (1.0 - DAMPING_FACTOR) + (DAMPING_FACTOR * dangling_mass)
        updated = {doi: base_factor * teleport[doi] for doi in nodes}
        for source, target_weights in transitions.items():
            for target, weight in target_weights.items():
                updated[target] += DAMPING_FACTOR * scores[source] * weight
        if sum(abs(updated[doi] - scores[doi]) for doi in nodes) < 1e-9:
            return updated
        scores = updated
    raise ValueError("Epistemic PageRank did not converge within 200 iterations")


def calculate_local_degrees(nodes: list[str], edges: list[CitationEdge]) -> dict[str, int]:
    """Count total incident citation edges (in + out) per node in the local subgraph."""
    node_set = set(nodes)
    degrees = {doi: 0 for doi in nodes}
    seen_pairs: set[tuple[str, str]] = set()
    for edge in edges:
        pair = (edge.source_key, edge.target_key)
        if pair in seen_pairs or edge.source_key not in node_set or edge.target_key not in node_set:
            continue
        seen_pairs.add(pair)
        degrees[edge.source_key] += 1
        degrees[edge.target_key] += 1
    return degrees


def calculate_ucb_frontier_priority(
    hybrid_score: float,
    bridge_balance: float,
    local_degree: int,
    expanded_count: int,
    depth: int = 1,
    exploration_constant: float = 0.15,
    depth_discount: float = 0.85,
) -> float:
    """Compute Epistemic Upper-Confidence-Bound (E-UCB) priority for multi-hop expansion."""
    exploration_bonus = exploration_constant * bridge_balance * math.sqrt(
        math.log(1.0 + max(1, expanded_count)) / (1.0 + max(0, local_degree))
    )
    decay = depth_discount ** max(0, depth - 1)
    return (hybrid_score + exploration_bonus) * decay


def compute_epistemic_hybrid_score(
    similarity_score: float,
    pagerank_score: float,
    epistemic_pagerank_score: float,
    bridge_balance: float,
    assessment: PaperEpistemicAssessment | None,
    similarity_weight: float,
    density_gated: bool = False,
    subgraph_density: float = 0.0,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> float:
    """Combine semantic similarity, Jev epistemic utility, E-PR, and bridge balance."""
    if not density_gated:
        if assessment is None:
            return (similarity_weight * similarity_score) + (
                (1.0 - similarity_weight) * pagerank_score
            )
        if assessment.prune_subtree:
            return (
                0.20 * max(0.0, similarity_score)
                + 0.10 * epistemic_pagerank_score
                + 0.70 * assessment.composite_epistemic_score
            )
        return (
            0.45 * similarity_score
            + 0.30 * assessment.composite_epistemic_score
            + 0.15 * epistemic_pagerank_score
            + 0.10 * bridge_balance
        )

    gate = calculate_density_gate(subgraph_density, steepness)
    if assessment is None:
        eff_sim_w, eff_pr_w = compute_density_gated_weights(
            similarity_weight, subgraph_density, steepness
        )
        return (eff_sim_w * similarity_score) + (eff_pr_w * pagerank_score)

    if assessment.prune_subtree:
        eff_epr_w = 0.10 * gate
        eff_sim_w = 0.20 + (0.10 - eff_epr_w)
        return (
            eff_sim_w * max(0.0, similarity_score)
            + eff_epr_w * epistemic_pagerank_score
            + 0.70 * assessment.composite_epistemic_score
        )

    eff_epr_w = 0.15 * gate
    eff_sim_w = 0.45 + (0.15 - eff_epr_w)
    return (
        eff_sim_w * similarity_score
        + 0.30 * assessment.composite_epistemic_score
        + eff_epr_w * epistemic_pagerank_score
        + 0.10 * bridge_balance
    )


def calculate_semantic_structural_dissonance(
    similarity_score: float | None,
    pagerank_score: float,
    max_pagerank: float,
) -> float | None:
    """Measure citation hub trap dissonance max(0, normalized_pagerank - similarity) in [0, 1]."""
    if similarity_score is None:
        return None
    normalized_pr = pagerank_score / max(1e-9, max_pagerank)
    clamped_sim = max(0.0, min(1.0, similarity_score))
    return min(1.0, max(0.0, normalized_pr - clamped_sim))


def classify_epistemic_diagnostic(
    similarity_score: float | None,
    dissonance: float | None,
    bridge_balance: float,
    assessment: PaperEpistemicAssessment | None,
    pruned: bool = False,
    steering: str | None = None,
    model_score: float | None = None,
) -> tuple[str | None, str | None]:
    """Produce a plain-language diagnostic badge and explanation for the researcher."""
    if steering == "suppress_hub":
        return (
            "hub_trap_suppressed",
            "You suppressed this paper. Its ranking weight is reduced and citation expansion is blocked.",
        )
    if pruned:
        return (
            "model_excluded",
            "Jev recommended excluding this paper. Citation expansion is blocked; this is a model judgment.",
        )
    if steering == "boost_gem":
        return "hidden_gem", "You prioritized this paper. The original Jev judgment has not changed."
    if dissonance is not None and dissonance >= 0.45:
        return (
            "citation_topic_mismatch",
            "This paper has high local citation centrality and a low topic match. This warning alone does not block expansion.",
        )
    if similarity_score is not None and similarity_score >= 0.72 and (dissonance or 0.0) <= 0.15:
        return (
            "strong_topic_match",
            "The abstract has a strong calculated match to your question. This is not a scientific quality check.",
        )
    if bridge_balance >= 0.75:
        return (
            "cross_question_bridge",
            "Balanced semantic relevance across multiple confirmed research questions.",
        )
    score = assessment.composite_epistemic_score if assessment is not None else model_score
    if score is not None and score >= 0.65:
        return (
            "model_alignment",
            "Jev gave this abstract a high alignment score. This is a model judgment, not verified scientific evidence.",
        )
    return None, None


def build_epistemic_paper_ranking(
    doi: str,
    similarity: SimilarityObservation | None,
    pagerank: float,
    epistemic_pagerank: float,
    bridge_balance: float | None,
    assessment: PaperEpistemicAssessment | None,
    threshold: float,
    similarity_weight: float,
    local_degree: int,
    expanded_count: int,
    max_pagerank: float = 1.0,
    density_gated: bool = False,
    subgraph_density: float = 0.0,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> PaperRanking:
    """Construct a PaperRanking enriched with E-GraphSelect epistemic metrics."""
    identity = identity_from_key(doi)
    if similarity is None:
        return PaperRanking(
            doi=identity.doi,
            corpus_id=identity.corpus_id,
            pagerank_score=pagerank,
            epistemic_pagerank_score=epistemic_pagerank,
            expansion_threshold=threshold,
            subgraph_density=subgraph_density if density_gated else None,
            density_gated=density_gated,
        )
    score = similarity.similarity_score
    bridge = bridge_balance if bridge_balance is not None else max(0.0, score)
    pruned = assessment.prune_subtree if assessment is not None else False
    hybrid = compute_epistemic_hybrid_score(
        score,
        pagerank,
        epistemic_pagerank,
        bridge,
        assessment,
        similarity_weight,
        density_gated=density_gated,
        subgraph_density=subgraph_density,
        steepness=steepness,
    )
    can_expand = (score >= threshold) and (not pruned)
    ucb_priority = calculate_ucb_frontier_priority(hybrid, bridge, local_degree, expanded_count)
    dissonance = calculate_semantic_structural_dissonance(score, pagerank, max_pagerank)
    badge, explanation = classify_epistemic_diagnostic(score, dissonance, bridge, assessment, pruned)
    return PaperRanking(
        doi=identity.doi,
        corpus_id=identity.corpus_id,
        question=similarity.question,
        similarity_score=score,
        pagerank_score=pagerank,
        hybrid_score=hybrid,
        expansion_threshold=threshold,
        can_expand=can_expand,
        embedding_version=EMBEDDING_VERSION,
        bridge_balance_score=bridge,
        jev_epistemic_score=assessment.composite_epistemic_score if assessment else None,
        jev_entropy=assessment.mean_entropy if assessment else None,
        jev_confidence=assessment.mean_confidence if assessment else None,
        jev_screening_label=assessment.screening_label if assessment else None,
        jev_pruned=pruned,
        epistemic_pagerank_score=epistemic_pagerank,
        ucb_frontier_priority=ucb_priority if can_expand else 0.0,
        jev_input_hash=assessment.input_hash if assessment else None,
        semantic_structural_dissonance=dissonance,
        epistemic_badge=badge,
        epistemic_explanation=explanation,
        subgraph_density=subgraph_density if density_gated else None,
        density_gated=density_gated,
    )


def calculate_epistemic_rankings(
    dois: list[str],
    edges: list[CitationEdge],
    similarities: list[SimilarityObservation],
    minimum_threshold: float,
    similarity_weight: float,
    assessments: dict[str, PaperEpistemicAssessment] | None = None,
    expanded_count: int = 1,
    density_gated: bool = False,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> list[PaperRanking]:
    """Compute E-GraphSelect rankings combining embeddings, Jev rubrics, E-PR, and E-UCB."""
    nodes = sorted(set(dois))
    if not nodes:
        return []
    best: dict[str, SimilarityObservation] = {}
    for observation in similarities:
        if (
            observation.paper_key not in best
            or observation.similarity_score > best[observation.paper_key].similarity_score
        ):
            best[observation.paper_key] = observation
    threshold = adaptive_threshold([item.similarity_score for item in best.values()], minimum_threshold)
    jev_map = assessments or {}
    bridge_map = compute_bridge_scores_by_doi(similarities)
    potentials = calculate_node_epistemic_potentials(nodes, best, jev_map)
    base_pagerank = citation_pagerank(nodes, edges)
    max_pr = max(base_pagerank.values(), default=1.0)
    epistemic_pr = calculate_epistemic_pagerank(nodes, edges, potentials)
    degrees = calculate_local_degrees(nodes, edges)
    density = calculate_candidate_subgraph_density(nodes, edges) if density_gated else 0.0
    return [
        build_epistemic_paper_ranking(
            doi=doi,
            similarity=best.get(doi),
            pagerank=base_pagerank[doi],
            epistemic_pagerank=epistemic_pr[doi],
            bridge_balance=bridge_map.get(doi),
            assessment=jev_map.get(doi),
            threshold=threshold,
            similarity_weight=similarity_weight,
            local_degree=degrees[doi],
            expanded_count=expanded_count,
            max_pagerank=max_pr,
            density_gated=density_gated,
            subgraph_density=density,
            steepness=steepness,
        )
        for doi in nodes
    ]


def calculate_density_gated_epistemic_rankings(
    dois: list[str],
    edges: list[CitationEdge],
    similarities: list[SimilarityObservation],
    minimum_threshold: float,
    similarity_weight: float,
    assessments: dict[str, PaperEpistemicAssessment] | None = None,
    expanded_count: int = 1,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> list[PaperRanking]:
    """Compute density-gated epistemic rankings."""
    return calculate_epistemic_rankings(
        dois=dois,
        edges=edges,
        similarities=similarities,
        minimum_threshold=minimum_threshold,
        similarity_weight=similarity_weight,
        assessments=assessments,
        expanded_count=expanded_count,
        density_gated=True,
        steepness=steepness,
    )


def steered_node_potential(ranking: PaperRanking, decision: str | None) -> float:
    """Compute node potential Phi(u) incorporating explicit researcher chat feedback."""
    if decision == "suppress_hub":
        return PRIOR_FLOOR
    if decision == "boost_gem":
        return 0.95
    if ranking.jev_pruned:
        return PRIOR_FLOOR
    sim = max(0.0, ranking.similarity_score or 0.0)
    jev_score = ranking.jev_epistemic_score if ranking.jev_epistemic_score is not None else sim
    return max(PRIOR_FLOOR, 0.50 * sim + 0.50 * jev_score)


def is_expansion_blocked(ranking: PaperRanking, decision: str | None) -> bool:
    if decision == "suppress_hub":
        return True
    if decision == "boost_gem":
        return False
    return ranking.jev_pruned


def effective_steering(ranking: PaperRanking, decisions: dict[str, str]) -> str | None:
    decision = decisions.get(ranking.paper_key, ranking.researcher_steering)
    return None if decision == "neutral" else decision


def restore_unsteered_ranking(ranking: PaperRanking) -> PaperRanking:
    if ranking.ranking_before_steering is None:
        return ranking
    values = ranking.ranking_before_steering.model_dump()
    values.update(
        {"ranking_before_steering": None, "researcher_steering": None, "steering_version": None}
    )
    return ranking.model_copy(update=values)


def rebuild_steered_ranking(
    ranking: PaperRanking,
    epistemic_pr: float,
    max_pagerank: float,
    decision: str | None,
    similarity_weight: float,
    local_degree: int,
    expanded_count: int,
) -> PaperRanking:
    """Update a single PaperRanking after interactive researcher steering."""
    active_decision = decision
    baseline = ranking.ranking_before_steering or RankingBeforeSteering.model_validate(
        ranking.model_dump(include=set(RankingBeforeSteering.model_fields))
    )
    if ranking.similarity_score is None:
        return ranking.model_copy(
            update={
                "epistemic_pagerank_score": epistemic_pr,
                "researcher_steering": active_decision,
                "steering_version": "preserve-model-v1" if active_decision else None,
                "ranking_before_steering": baseline,
            }
        )
    sim = ranking.similarity_score
    bridge = ranking.bridge_balance_score if ranking.bridge_balance_score is not None else max(0.0, sim)
    pruned = is_expansion_blocked(ranking, active_decision)
    jev_score = ranking.jev_epistemic_score
    if active_decision == "boost_gem":
        jev_score = max(jev_score or 0.0, 0.90)
    elif active_decision == "suppress_hub":
        jev_score = min(jev_score if jev_score is not None else 0.05, 0.05)
    hybrid = (
        0.20 * max(0.0, sim) + 0.10 * epistemic_pr + 0.70 * (jev_score or 0.0)
        if pruned
        else 0.45 * sim
        + 0.30 * (jev_score if jev_score is not None else sim)
        + 0.15 * epistemic_pr
        + 0.10 * bridge
    )
    if active_decision is None and ranking.jev_epistemic_score is None:
        hybrid = similarity_weight * sim + (1.0 - similarity_weight) * ranking.pagerank_score
    can_expand = (sim >= ranking.expansion_threshold) and (not pruned)
    dissonance = calculate_semantic_structural_dissonance(sim, ranking.pagerank_score, max_pagerank)
    badge, explanation = classify_epistemic_diagnostic(
        sim,
        dissonance,
        bridge,
        None,
        pruned,
        active_decision,
        ranking.jev_epistemic_score,
    )
    return ranking.model_copy(
        update={
            "hybrid_score": hybrid,
            "can_expand": can_expand,
            "epistemic_pagerank_score": epistemic_pr,
            "ucb_frontier_priority": calculate_ucb_frontier_priority(
                hybrid, bridge, local_degree, expanded_count
            )
            if can_expand
            else 0.0,
            "semantic_structural_dissonance": dissonance,
            "epistemic_badge": badge,
            "epistemic_explanation": explanation,
            "researcher_steering": active_decision,
            "steering_version": "preserve-model-v1" if active_decision else None,
            "ranking_before_steering": baseline,
        }
    )


def apply_researcher_epistemic_steering(
    rankings: list[PaperRanking],
    edges: list[CitationEdge],
    steering_decisions: dict[str, str],
    similarity_weight: float = 0.50,
) -> list[PaperRanking]:
    """Re-run Epistemic PageRank incorporating researcher Hidden-Gem boosts or Hub-Trap suppressions."""
    if not rankings:
        return []
    nodes = sorted({item.paper_key for item in rankings})
    by_doi = {item.paper_key: item for item in rankings}
    decisions = {doi: effective_steering(by_doi[doi], steering_decisions) for doi in nodes}
    if not any(decisions.values()):
        return [restore_unsteered_ranking(by_doi[doi]) for doi in nodes]
    potentials = {doi: steered_node_potential(by_doi[doi], decisions[doi]) for doi in nodes}
    epistemic_pr = calculate_epistemic_pagerank(nodes, edges, potentials)
    degrees = calculate_local_degrees(nodes, edges)
    max_pr = max((item.pagerank_score for item in rankings), default=1.0)
    return [
        rebuild_steered_ranking(
            by_doi[doi],
            epistemic_pr[doi],
            max_pr,
            decisions[doi],
            similarity_weight,
            degrees[doi],
            len(nodes),
        )
        for doi in nodes
    ]
