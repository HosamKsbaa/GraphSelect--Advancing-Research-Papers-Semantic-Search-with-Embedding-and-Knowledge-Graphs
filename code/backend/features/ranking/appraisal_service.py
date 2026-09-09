"""Autonomous Multi-Agent Appraisal & Strategic Recommendations Service for ALRS GraphSelect.

Implements candidate pool partitioning, mathematical scoring into 3 archetypes
(Foundational Prior Art, Contemporary Breakthroughs, Topological Bridges),
Burt's structural hole bridging centrality (C_B(v) = B(v) * BC(v) per Constitution A52),
evidence-grounded academic rationales, and 4 structured follow-up steering actions.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from features.ranking.models import (
    CandidatePaperState,
    SteeringActionOption,
    TraversalAppraisalResult,
)
from features.search.models import OneHopExpansionResult

logger = logging.getLogger(__name__)


def compute_bridging_coefficient(degree: int, neighbor_degrees: list[int]) -> float:
    """Compute Burt's bridging coefficient B(v) = (1/d(v)) * sum(1/d(j))."""
    if degree <= 0 or not neighbor_degrees:
        return 0.0
    reciprocal_sum = sum(1.0 / max(1, d) for d in neighbor_degrees)
    return reciprocal_sum / float(degree)


def compute_bridging_centrality(
    bridging_coefficient: float,
    betweenness_centrality: float,
) -> float:
    """Compute Burt's structural hole bridging centrality C_B(v) = B(v) * BC(v)."""
    return float(bridging_coefficient * max(0.0, betweenness_centrality))


def classify_structural_archetype(scores: dict[str, float]) -> str:
    """Map highest archetype score to standardized partition name."""
    mapping = {
        "foundational": "foundational_prior_art",
        "contemporary": "contemporary_breakthroughs",
        "bridge": "topological_bridges",
    }
    best_key = max(scores, key=lambda k: scores.get(k, 0.0))
    return mapping[best_key]


def _extract_primary_rq(similarity_scores: list[dict[str, Any]]) -> str:
    """Extract the primary (highest-scoring) Research Question text or ID."""
    if not similarity_scores:
        return "General Topic Relevance"
    best = max(similarity_scores, key=lambda s: float(s.get("score", 0.0)))
    return str(best.get("question") or best.get("question_id") or "Active Research Question")


def _format_authors_summary(authors: list[str]) -> str:
    """Format authors list into concise citation format."""
    if not authors:
        return "Unknown Authors"
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} & {authors[1]}"
    return f"{authors[0]} et al."


def _foundational_rationale(paper: CandidatePaperState, year: str, venue: str, rq: str) -> str:
    """Build rationale for foundational prior art."""
    phrase = "direct backward reference cited by seed" if paper.direction == "backward_reference" else "high-authority prior work"
    return (
        f"Seminal foundational work ({year}{venue}) with {paper.citation_count:,} global citations "
        f"and {phrase}. Provides theoretical foundations and baseline architecture "
        f"relevant to '{rq}' (relevance score: {paper.max_similarity:.2f})."
    )


def _contemporary_rationale(paper: CandidatePaperState, year: str, venue: str, rq: str) -> str:
    """Build rationale for contemporary breakthrough."""
    phrase = "forward citation extending seed" if paper.direction == "forward_citation" else "recent publication"
    return (
        f"Recent breakthrough ({year}{venue}) with {phrase} and strong semantic alignment "
        f"(cosine similarity: {paper.max_similarity:.2f}) with '{rq}'. Demonstrates novel empirical improvements "
        f"and recent domain advances."
    )


def _bridge_rationale(paper: CandidatePaperState, year: str, venue: str, rq: str) -> str:
    """Build rationale for topological bridge."""
    rq_count = len(paper.similarity_scores)
    rq_phrase = f"across {rq_count} project research questions" if rq_count > 1 else f"for '{rq}'"
    return (
        f"Topological bridge paper ({year}{venue}) with in-graph degree of {paper.in_graph_degree} "
        f"and PageRank centrality of {paper.pagerank_score:.3f}. Connects distinct citation subclusters and exhibits "
        f"balanced cross-cutting relevance {rq_phrase} (max similarity: {paper.max_similarity:.2f})."
    )


def _generate_candidate_rationale(paper: CandidatePaperState, archetype: str, current_year: int = 2026) -> str:
    """Generate evidence-grounded academic rationale for a candidate paper."""
    year_str = str(paper.year) if paper.year is not None else "undated"
    venue_str = f" in {paper.venue}" if paper.venue else ""
    primary_rq = paper.primary_rq or _extract_primary_rq(paper.similarity_scores)
    if archetype == "foundational_prior_art":
        return _foundational_rationale(paper, year_str, venue_str, primary_rq)
    if archetype == "contemporary_breakthroughs":
        return _contemporary_rationale(paper, year_str, venue_str, primary_rq)
    return _bridge_rationale(paper, year_str, venue_str, primary_rq)



def _compute_normalization_denominators(
    raw_candidates: list[CandidatePaperState],
) -> tuple[float, int, float]:
    """Compute normalization denominators across candidate pool."""
    max_log_cites = max(
        [math.log1p(max(0, c.citation_count)) for c in raw_candidates] + [1.0]
    )
    if max_log_cites <= 0.0:
        max_log_cites = 1.0
    max_degree = max([max(1, c.in_graph_degree) for c in raw_candidates] + [1])
    max_pagerank = max([max(0.0, c.pagerank_score) for c in raw_candidates] + [0.001])
    if max_pagerank <= 0.0:
        max_pagerank = 1.0
    return max_log_cites, max_degree, max_pagerank


def _score_foundational(
    cand: CandidatePaperState,
    log_cit_norm: float,
    current_year: int,
    weights: tuple[float, float, float, float],
) -> float:
    """Compute foundational prior art score."""
    w1, w2, w3, w4 = weights
    age = max(0, current_year - cand.year) if cand.year is not None else 3
    bwd_term = 1.0 if cand.direction in ("backward_reference", "both") else 0.0
    age_maturity = min(1.0, age / 5.0)
    s_avg = cand.mean_similarity if cand.mean_similarity > 0 else cand.max_similarity
    h = w1 * log_cit_norm + w2 * bwd_term + w3 * age_maturity + w4 * s_avg
    if cand.year is not None and cand.year <= (current_year - 3):
        h += 0.10
    if cand.direction == "backward_reference":
        h += 0.05
    return h


def _score_contemporary(
    cand: CandidatePaperState,
    log_cit_norm: float,
    current_year: int,
    weights: tuple[float, float, float],
) -> float:
    """Compute contemporary breakthrough score."""
    mu1, mu2, mu3 = weights
    age = max(0, current_year - cand.year) if cand.year is not None else 3
    recency = max(0.0, 1.0 - (age / 3.0))
    s_max = cand.max_similarity
    h = mu1 * s_max + mu2 * recency + mu3 * log_cit_norm
    if cand.year is not None and cand.year >= (current_year - 2) and s_max >= 0.60:
        h += 0.15
    elif cand.year is not None and cand.year >= (current_year - 2):
        h += 0.05
    return h


def _compute_multi_rq_balance(sim_scores: list[dict[str, Any]]) -> float:
    """Compute multi-research-question balance score."""
    if len(sim_scores) < 2:
        return 0.5
    num_scores = [float(s.get("score", 0.0)) for s in sim_scores]
    spread = max(num_scores) - min(num_scores)
    balance = max(0.0, 1.0 - spread)
    ratio = (min(num_scores) / max(num_scores)) if max(num_scores) > 0 else 1.0
    return 0.6 * balance + 0.4 * ratio


def _score_bridge(
    cand: CandidatePaperState,
    max_pagerank: float,
    max_degree: int,
    weights: tuple[float, float, float],
) -> float:
    """Compute topological bridge score."""
    g1, g2, g3 = weights
    pr_norm = min(1.0, cand.pagerank_score / max_pagerank) if max_pagerank > 0 else 0.5
    deg_norm = min(1.0, cand.in_graph_degree / max_degree) if max_degree > 0 else 0.5
    balance = _compute_multi_rq_balance(cand.similarity_scores or [])
    h = g1 * pr_norm + g2 * deg_norm + g3 * balance
    if cand.in_graph_degree > 1 or cand.pagerank_score > 0.0:
        h += 0.05
    return h


def _build_evaluated_candidate(
    cand: CandidatePaperState, scores_dict: dict[str, float], partition_name: str, current_year: int
) -> CandidatePaperState:
    """Build and decorate CandidatePaperState with scores and rationale."""
    cand_dict = cand.model_dump()
    cand_dict["archetype_scores"] = scores_dict
    cand_dict["primary_rq"] = _extract_primary_rq(cand.similarity_scores or [])
    cand_dict["partition"] = partition_name
    evaluated = CandidatePaperState(**cand_dict)
    evaluated.recommendation_rationale = _generate_candidate_rationale(
        evaluated, partition_name, current_year=current_year
    )
    return evaluated


def _evaluate_single_candidate(
    cand: CandidatePaperState,
    max_log_cites: float,
    max_degree: int,
    max_pagerank: float,
    current_year: int,
    weights: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]],
) -> CandidatePaperState:
    """Score a single candidate paper and decorate with partition and rationale."""
    c_p = max(0, cand.citation_count)
    log_cit_norm = math.log1p(c_p) / max_log_cites
    h_found = _score_foundational(cand, log_cit_norm, current_year, weights[0])  # type: ignore[arg-type]
    h_contemp = _score_contemporary(cand, log_cit_norm, current_year, weights[1])  # type: ignore[arg-type]
    h_bridge = _score_bridge(cand, max_pagerank, max_degree, weights[2])  # type: ignore[arg-type]
    scores_dict = {
        "foundational": round(float(h_found), 4),
        "contemporary": round(float(h_contemp), 4),
        "bridge": round(float(h_bridge), 4),
    }
    partition_name = classify_structural_archetype(scores_dict)
    return _build_evaluated_candidate(cand, scores_dict, partition_name, current_year)


def _partition_and_sort(
    evaluated: list[CandidatePaperState],
) -> tuple[list[CandidatePaperState], list[CandidatePaperState], list[CandidatePaperState]]:
    """Group evaluated candidates into partitions and sort by archetype criteria."""
    f_list = [c for c in evaluated if c.partition == "foundational_prior_art"]
    c_list = [c for c in evaluated if c.partition == "contemporary_breakthroughs"]
    b_list = [c for c in evaluated if c.partition == "topological_bridges"]

    f_list.sort(key=lambda c: (-c.archetype_scores.get("foundational", 0.0), -c.citation_count, -c.max_similarity))
    c_list.sort(key=lambda c: (-c.archetype_scores.get("contemporary", 0.0), -c.max_similarity, -(c.year or 0)))
    b_list.sort(key=lambda c: (-c.archetype_scores.get("bridge", 0.0), -c.in_graph_degree, -c.pagerank_score, -c.max_similarity))
    return f_list, c_list, b_list


def _resolve_top_candidates(
    evaluated: list[CandidatePaperState],
    f_list: list[CandidatePaperState],
    c_list: list[CandidatePaperState],
    b_list: list[CandidatePaperState],
) -> tuple[CandidatePaperState, CandidatePaperState, CandidatePaperState]:
    """Resolve top representative paper per archetype with fallbacks."""
    all_by_found = sorted(evaluated, key=lambda c: (-c.archetype_scores.get("foundational", 0.0), -c.citation_count))
    all_by_contemp = sorted(evaluated, key=lambda c: (-c.archetype_scores.get("contemporary", 0.0), -c.max_similarity))
    all_by_bridge = sorted(evaluated, key=lambda c: (-c.archetype_scores.get("bridge", 0.0), -c.in_graph_degree))
    top_f = f_list[0] if f_list else all_by_found[0]
    top_c = c_list[0] if c_list else all_by_contemp[0]
    top_b = b_list[0] if b_list else all_by_bridge[0]
    return top_f, top_c, top_b


def _create_single_steering_option(
    opt_id: str, label_prefix: str, cand: CandidatePaperState, rationale: str
) -> SteeringActionOption:
    """Helper to create a single deep expansion steering option."""
    return SteeringActionOption(
        option_id=opt_id,
        action_type="expand_deeper",
        target_doi=cand.doi,
        target_title=cand.title,
        label=f"Expand 1 Hop on {label_prefix} ({cand.doi})",
        rationale=rationale,
    )


def _create_steering_options(
    top_f: CandidatePaperState,
    top_c: CandidatePaperState,
    top_b: CandidatePaperState,
) -> list[SteeringActionOption]:
    """Build the 4 structured SteeringActionOption items."""
    configs = [
        ("option_a_foundational", "Foundational Art", top_f, f"Deep dive into theoretical roots of '{top_f.title}' ({top_f.year or 'undated'})."),
        ("option_b_contemporary", "Contemporary Breakthrough", top_c, f"Explore advances of '{top_c.title}' ({top_c.year or 'undated'})."),
        ("option_c_bridge", "Topological Bridge", top_b, f"Traverse structural bridge '{top_b.title}' connecting multiple questions."),
    ]
    options = [_create_single_steering_option(i, l, c, r) for i, l, c, r in configs]
    options.append(
        SteeringActionOption(
            option_id="option_d_adopt_finalize",
            action_type="add_to_library",
            label="Add Top Candidates to Project Library & Conclude Cycle",
            rationale="Adopt top discovered papers into permanent project library and finalize cycle.",
        )
    )
    return options


def _format_archetype_sections(
    f_list: list[CandidatePaperState],
    c_list: list[CandidatePaperState],
    b_list: list[CandidatePaperState],
) -> list[str]:
    """Format markdown section lines for discovered archetypes."""
    lines: list[str] = []
    sections = [
        ("🏛️ Foundational Prior Art", f_list),
        ("⚡ Contemporary Breakthroughs", c_list),
        ("🌉 Topological Bridges", b_list),
    ]
    for header, plist in sections:
        if plist:
            lines.append(f"#### {header} ({len(plist)} papers)")
            for p in plist[:2]:
                lines.extend([f"- **[{p.doi}] {p.title}** ({p.year or 'N/A'})", f"  *Rationale*: {p.recommendation_rationale}"])
            lines.append("")
    return lines


def _format_strategic_recommendation(
    seed_doi: str,
    total_discovered: int,
    f_list: list[CandidatePaperState],
    c_list: list[CandidatePaperState],
    b_list: list[CandidatePaperState],
    steering_options: list[SteeringActionOption],
) -> str:
    """Format markdown strategic recommendation summary."""
    lines = [
        f"### 🎯 Strategic Traversal Appraisal (Seed: `{seed_doi}`)",
        f"Evaluated **{total_discovered} candidate papers** across 3 topological and semantic archetypes:\n",
    ]
    lines.extend(_format_archetype_sections(f_list, c_list, b_list))
    lines.append("#### 🧭 Strategic Steering Choices:")
    for opt in steering_options:
        lines.append(f"- **{opt.label}**: {opt.rationale}")
    return "\n".join(lines)


def _handle_empty_candidates(one_hop: OneHopExpansionResult) -> TraversalAppraisalResult:
    """Construct empty appraisal result with fallback steering option."""
    fallback = SteeringActionOption(
        option_id="option_d_adopt_finalize",
        action_type="conclude",
        label="Conclude Traversal Cycle",
        rationale="No 1-hop candidates discovered. Conclude cycle or select an alternative seed.",
    )
    return TraversalAppraisalResult(
        seed_doi=one_hop.seed_doi,
        seed_title=one_hop.seed_title or f"Paper {one_hop.seed_doi}",
        cycle_level=one_hop.cycle_level,
        strategic_recommendation=f"No 1-hop candidate papers discovered for seed {one_hop.seed_doi}.",
        steering_options=[fallback],
    )


def _build_appraisal_result(
    one_hop_result: OneHopExpansionResult,
    raw_count: int,
    f_list: list[CandidatePaperState],
    c_list: list[CandidatePaperState],
    b_list: list[CandidatePaperState],
    options: list[SteeringActionOption],
    rec: str,
) -> TraversalAppraisalResult:
    """Package appraisal components into TraversalAppraisalResult."""
    return TraversalAppraisalResult(
        seed_doi=one_hop_result.seed_doi,
        seed_title=one_hop_result.seed_title or f"Paper {one_hop_result.seed_doi}",
        cycle_level=one_hop_result.cycle_level,
        total_discovered=raw_count,
        total_new=one_hop_result.total_new,
        foundational_prior_art=f_list,
        contemporary_breakthroughs=c_list,
        topological_bridges=b_list,
        strategic_recommendation=rec,
        steering_options=options,
    )


def _evaluate_all_candidates(
    raw: list[CandidatePaperState], current_year: int, weights: tuple[Any, ...]
) -> list[CandidatePaperState]:
    """Normalize and evaluate all candidates."""
    max_cites, max_deg, max_pr = _compute_normalization_denominators(raw)
    return [
        _evaluate_single_candidate(c, max_cites, max_deg, max_pr, current_year, weights)  # type: ignore[arg-type]
        for c in raw
    ]


def appraise_1hop_candidate_pool(
    one_hop_result: OneHopExpansionResult,
    research_questions: list[str] | list[dict[str, Any]] | None = None,
    current_year: int = 2026,
    foundational_weights: tuple[float, float, float, float] = (0.35, 0.25, 0.20, 0.20),
    contemporary_weights: tuple[float, float, float] = (0.50, 0.35, 0.15),
    bridge_weights: tuple[float, float, float] = (0.40, 0.30, 0.30),
) -> TraversalAppraisalResult:
    """Evaluate discovered candidate papers from 1-hop traversal into 3 archetypes."""
    raw = one_hop_result.candidates or []
    if not raw:
        return _handle_empty_candidates(one_hop_result)
    weights = (foundational_weights, contemporary_weights, bridge_weights)
    evaluated = _evaluate_all_candidates(raw, current_year, weights)
    f_list, c_list, b_list = _partition_and_sort(evaluated)
    top_f, top_c, top_b = _resolve_top_candidates(evaluated, f_list, c_list, b_list)
    options = _create_steering_options(top_f, top_c, top_b)
    rec = _format_strategic_recommendation(one_hop_result.seed_doi, len(raw), f_list, c_list, b_list, options)
    return _build_appraisal_result(one_hop_result, len(raw), f_list, c_list, b_list, options, rec)
