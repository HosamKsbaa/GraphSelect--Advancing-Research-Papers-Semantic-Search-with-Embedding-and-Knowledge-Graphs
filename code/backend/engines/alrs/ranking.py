"""GraphSelect ranking observations, PageRank, and density-gated weight reallocation.

Ported from archive commit 865cd08 (`code/backend/alrs_tool/search/ranking_models.py`).
"""

from __future__ import annotations

import hashlib
import math
from typing import Literal

from pydantic import BaseModel, Field

from engines.papers import CitationEdge, Paper, PaperIdentity, identity_from_key

EMBEDDING_VERSION = "gemini-embedding-2:768:retrieval-v1"
DEFAULT_DENSITY_STEEPNESS: float = 20.0


class SimilarityObservation(PaperIdentity):
    question: str
    similarity_score: float = Field(ge=-1, le=1)


class RankingBeforeSteering(BaseModel):
    hybrid_score: float | None
    can_expand: bool
    epistemic_pagerank_score: float | None
    ucb_frontier_priority: float | None
    semantic_structural_dissonance: float | None
    epistemic_badge: str | None
    epistemic_explanation: str | None


class PaperRanking(PaperIdentity):
    question: str | None = None
    similarity_score: float | None = None
    pagerank_score: float
    hybrid_score: float | None = None
    expansion_threshold: float
    can_expand: bool = False
    embedding_version: str | None = None
    bridge_balance_score: float | None = None
    jev_epistemic_score: float | None = None
    jev_entropy: float | None = None
    jev_confidence: float | None = None
    jev_screening_label: str | None = None
    jev_pruned: bool = False
    epistemic_pagerank_score: float | None = None
    ucb_frontier_priority: float | None = None
    jev_input_hash: str | None = None
    semantic_structural_dissonance: float | None = None
    epistemic_badge: str | None = None
    epistemic_explanation: str | None = None
    researcher_steering: str | None = None
    steering_version: Literal["preserve-model-v1"] | None = None
    ranking_before_steering: RankingBeforeSteering | None = None
    subgraph_density: float | None = None
    density_gated: bool = False


def paper_embedding_hash(paper: Paper) -> str:
    text = f"title: {paper.title} | text: {paper.abstract or ''}"
    return hashlib.sha256(text.encode()).hexdigest()


def adaptive_threshold(scores: list[float], minimum: float) -> float:
    if not scores:
        return minimum
    mean = sum(scores) / len(scores)
    variance = sum((score - mean) ** 2 for score in scores) / len(scores)
    return max(minimum, mean - math.sqrt(variance))


def citation_pagerank(dois: list[str], edges: list[CitationEdge]) -> dict[str, float]:
    """Compute PageRank on the saved local citation graph without fabricated fallback."""
    nodes = sorted(set(dois))
    if not nodes:
        return {}
    outgoing: dict[str, set[str]] = {doi: set() for doi in nodes}
    for edge in edges:
        if edge.source_key in outgoing and edge.target_key in outgoing:
            outgoing[edge.source_key].add(edge.target_key)
    scores = {doi: 1.0 / len(nodes) for doi in nodes}
    for _ in range(200):
        dangling = sum(scores[doi] for doi in nodes if not outgoing[doi])
        updated = {doi: (0.15 + 0.85 * dangling) / len(nodes) for doi in nodes}
        for source, targets in outgoing.items():
            for target in targets:
                updated[target] += 0.85 * scores[source] / len(targets)
        if sum(abs(updated[doi] - scores[doi]) for doi in nodes) < 1e-9:
            return updated
        scores = updated
    raise ValueError("Local PageRank did not converge within 200 iterations")


def calculate_subgraph_density_from_counts(
    node_count: int,
    edge_count: int,
) -> float:
    """Calculate candidate subgraph edge density rho in [0.0, 1.0]."""
    if node_count <= 1:
        return 0.0
    max_possible = node_count * (node_count - 1) / 2.0
    if max_possible <= 0.0:
        return 0.0
    return min(1.0, max(0.0, edge_count / max_possible))


def calculate_candidate_subgraph_density(
    nodes: list[str],
    edges: list[CitationEdge],
) -> float:
    """Calculate candidate subgraph directed or undirected citation density in [0.0, 1.0]."""
    node_set = set(nodes)
    if len(node_set) <= 1:
        return 0.0
    seen_edges: set[tuple[str, str]] = set()
    for edge in edges:
        if (
            edge.source_key in node_set
            and edge.target_key in node_set
            and edge.source_key != edge.target_key
        ):
            seen_edges.add((edge.source_key, edge.target_key))
    return calculate_subgraph_density_from_counts(len(node_set), len(seen_edges))


def calculate_density_gate(
    density: float,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> float:
    """Compute smooth saturation gate g(rho) = tanh(steepness * rho) in [0.0, 1.0]."""
    if density <= 0.0:
        return 0.0
    return min(1.0, max(0.0, math.tanh(steepness * density)))


def compute_density_gated_weights(
    base_similarity_weight: float = 0.70,
    density: float = 0.0,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> tuple[float, float]:
    """Compute (effective_similarity_weight, effective_pagerank_weight) for ALRS."""
    base_pr_weight = 1.0 - base_similarity_weight
    gate = calculate_density_gate(density, steepness)
    eff_pr_weight = min(base_pr_weight, max(0.0, base_pr_weight * gate))
    eff_sim_weight = 1.0 - eff_pr_weight
    return eff_sim_weight, eff_pr_weight


def calculate_rankings(
    dois: list[str],
    edges: list[CitationEdge],
    similarities: list[SimilarityObservation],
    minimum_threshold: float,
    similarity_weight: float,
    density_gated: bool = False,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> list[PaperRanking]:
    best: dict[str, SimilarityObservation] = {}
    for observation in similarities:
        if (
            observation.paper_key not in best
            or observation.similarity_score > best[observation.paper_key].similarity_score
        ):
            best[observation.paper_key] = observation
    threshold = adaptive_threshold([item.similarity_score for item in best.values()], minimum_threshold)
    centrality = citation_pagerank(dois, edges)
    if not density_gated:
        return [
            rank_paper(doi, best.get(doi), centrality[doi], threshold, similarity_weight)
            for doi in sorted(centrality)
        ]

    nodes = sorted(centrality)
    density = calculate_candidate_subgraph_density(nodes, edges)
    eff_sim_w, eff_pr_w = compute_density_gated_weights(similarity_weight, density, steepness)
    return [
        rank_paper_density_gated(
            doi,
            best.get(doi),
            centrality[doi],
            threshold,
            eff_sim_w,
            eff_pr_w,
            density,
        )
        for doi in nodes
    ]


def calculate_density_gated_rankings(
    dois: list[str],
    edges: list[CitationEdge],
    similarities: list[SimilarityObservation],
    minimum_threshold: float,
    similarity_weight: float,
    steepness: float = DEFAULT_DENSITY_STEEPNESS,
) -> list[PaperRanking]:
    """Calculate density-gated baseline ALRS rankings."""
    return calculate_rankings(
        dois=dois,
        edges=edges,
        similarities=similarities,
        minimum_threshold=minimum_threshold,
        similarity_weight=similarity_weight,
        density_gated=True,
        steepness=steepness,
    )


def rank_paper(
    doi: str,
    similarity: SimilarityObservation | None,
    pagerank: float,
    threshold: float,
    weight: float,
) -> PaperRanking:
    identity = identity_from_key(doi)
    if similarity is None:
        return PaperRanking(
            doi=identity.doi,
            corpus_id=identity.corpus_id,
            pagerank_score=pagerank,
            expansion_threshold=threshold,
        )
    score = similarity.similarity_score
    return PaperRanking(
        doi=identity.doi,
        corpus_id=identity.corpus_id,
        question=similarity.question,
        similarity_score=score,
        pagerank_score=pagerank,
        hybrid_score=weight * score + (1 - weight) * pagerank,
        expansion_threshold=threshold,
        can_expand=score >= threshold,
        embedding_version=EMBEDDING_VERSION,
    )


def rank_paper_density_gated(
    doi: str,
    similarity: SimilarityObservation | None,
    pagerank: float,
    threshold: float,
    eff_similarity_weight: float,
    eff_pagerank_weight: float,
    subgraph_density: float,
) -> PaperRanking:
    identity = identity_from_key(doi)
    if similarity is None:
        return PaperRanking(
            doi=identity.doi,
            corpus_id=identity.corpus_id,
            pagerank_score=pagerank,
            expansion_threshold=threshold,
            subgraph_density=subgraph_density,
            density_gated=True,
        )
    score = similarity.similarity_score
    hybrid = eff_similarity_weight * score + eff_pagerank_weight * pagerank
    return PaperRanking(
        doi=identity.doi,
        corpus_id=identity.corpus_id,
        question=similarity.question,
        similarity_score=score,
        pagerank_score=pagerank,
        hybrid_score=hybrid,
        expansion_threshold=threshold,
        can_expand=score >= threshold,
        embedding_version=EMBEDDING_VERSION,
        subgraph_density=subgraph_density,
        density_gated=True,
    )
