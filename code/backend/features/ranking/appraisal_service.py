"""Autonomous Multi-Agent Appraisal & Strategic Recommendations Service for ALRS GraphSelect.

Implements candidate pool partitioning, mathematical scoring into 3 archetypes
(Foundational Prior Art, Contemporary Breakthroughs, Topological Bridges),
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


def _extract_primary_rq(similarity_scores: list[dict[str, Any]]) -> str:
    """Extract the primary (highest-scoring) Research Question text or ID."""
    if not similarity_scores:
        return "General Topic Relevance"
    best = max(similarity_scores, key=lambda s: float(s.get("score", 0.0)))
    return best.get("question") or best.get("question_id") or "Active Research Question"


def _format_authors_summary(authors: list[str]) -> str:
    """Format authors list into concise citation format."""
    if not authors:
        return "Unknown Authors"
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} & {authors[1]}"
    return f"{authors[0]} et al."


def _generate_candidate_rationale(
    paper: CandidatePaperState,
    archetype: str,
    current_year: int = 2026,
) -> str:
    """Generate an evidence-grounded academic rationale for a candidate paper."""
    authors_str = _format_authors_summary(paper.authors)
    year_str = str(paper.year) if paper.year is not None else "undated"
    venue_str = f" in {paper.venue}" if paper.venue else ""
    primary_rq = paper.primary_rq or _extract_primary_rq(paper.similarity_scores)
    max_sim = paper.max_similarity

    if archetype == "foundational_prior_art":
        direction_phrase = (
            "direct backward reference cited by seed"
            if paper.direction == "backward_reference"
            else "high-authority prior work"
        )
        return (
            f"Seminal foundational work ({year_str}{venue_str}) with {paper.citation_count:,} global citations "
            f"and {direction_phrase}. Provides theoretical foundations and baseline architecture "
            f"relevant to '{primary_rq}' (relevance score: {max_sim:.2f})."
        )

    if archetype == "contemporary_breakthroughs":
        direction_phrase = (
            "forward citation extending seed"
            if paper.direction == "forward_citation"
            else "recent publication"
        )
        return (
            f"Recent breakthrough ({year_str}{venue_str}) with {direction_phrase} and strong semantic alignment "
            f"(cosine similarity: {max_sim:.2f}) with '{primary_rq}'. Demonstrates novel empirical improvements "
            f"and recent domain advances."
        )

    # topological_bridges
    rq_count = len(paper.similarity_scores)
    rq_phrase = (
        f"across {rq_count} project research questions"
        if rq_count > 1
        else f"for '{primary_rq}'"
    )
    return (
        f"Topological bridge paper ({year_str}{venue_str}) with in-graph degree of {paper.in_graph_degree} "
        f"and PageRank centrality of {paper.pagerank_score:.3f}. Connects distinct citation subclusters and exhibits "
        f"balanced cross-cutting relevance {rq_phrase} (max similarity: {max_sim:.2f})."
    )


def appraise_1hop_candidate_pool(
    one_hop_result: OneHopExpansionResult,
    research_questions: list[str] | list[dict[str, Any]] | None = None,
    current_year: int = 2026,
    foundational_weights: tuple[float, float, float, float] = (0.35, 0.25, 0.20, 0.20),
    contemporary_weights: tuple[float, float, float] = (0.50, 0.35, 0.15),
    bridge_weights: tuple[float, float, float] = (0.40, 0.30, 0.30),
) -> TraversalAppraisalResult:
    """Evaluate discovered candidate papers from 1-hop traversal into 3 archetypes with steering options.

    Partitions the candidate pool into:
      1. Foundational Prior Art (high backward references, global citations, mature age >= 3 years)
      2. Contemporary Breakthroughs (high cosine similarity >= 0.60, recent publication year 2024–2026)
      3. Topological Bridges (high graph PageRank / in-graph degree, multi-RQ balanced relevance)

    Args:
        one_hop_result: Result object from bounded 1-hop expansion.
        research_questions: Optional list of active project research questions.
        current_year: Reference year for maturity/recency calculations (default 2026).
        foundational_weights: Weights (w1=cites, w2=backward_dir, w3=age_maturity, w4=avg_sim).
        contemporary_weights: Weights (mu1=max_sim, mu2=recency, mu3=momentum).
        bridge_weights: Weights (gamma1=pagerank, gamma2=in_degree, gamma3=multi_rq_balance).

    Returns:
        TraversalAppraisalResult containing partitioned candidate lists, rationales, and 4 steering options.
    """
    raw_candidates = one_hop_result.candidates or []
    seed_doi = one_hop_result.seed_doi
    seed_title = one_hop_result.seed_title or f"Paper {seed_doi}"
    total_discovered = len(raw_candidates)

    if not raw_candidates:
        fallback_option = SteeringActionOption(
            option_id="option_d_adopt_finalize",
            action_type="conclude",
            target_doi=None,
            target_title=None,
            label="Conclude Traversal Cycle",
            rationale="No 1-hop candidates were discovered. Conclude cycle or select an alternative seed paper.",
        )
        return TraversalAppraisalResult(
            seed_doi=seed_doi,
            seed_title=seed_title,
            cycle_level=one_hop_result.cycle_level,
            total_discovered=0,
            total_new=0,
            foundational_prior_art=[],
            contemporary_breakthroughs=[],
            topological_bridges=[],
            strategic_recommendation=f"No 1-hop candidate papers discovered for seed {seed_doi} ('{seed_title}').",
            steering_options=[fallback_option],
        )

    # 1. Compute normalization denominators across the candidate pool
    max_log_cites = max(
        [math.log1p(max(0, c.citation_count)) for c in raw_candidates] + [1.0]
    )
    if max_log_cites <= 0.0:
        max_log_cites = 1.0

    max_degree = max([max(1, c.in_graph_degree) for c in raw_candidates] + [1])
    max_pagerank = max([max(0.0, c.pagerank_score) for c in raw_candidates] + [0.001])
    if max_pagerank <= 0.0:
        max_pagerank = 1.0

    # 2. Evaluate scores for each candidate paper
    evaluated_candidates: list[CandidatePaperState] = []
    w1, w2, w3, w4 = foundational_weights
    mu1, mu2, mu3 = contemporary_weights
    gamma1, gamma2, gamma3 = bridge_weights

    for cand in raw_candidates:
        c_p = max(0, cand.citation_count)
        log_cit_norm = math.log1p(c_p) / max_log_cites

        y_p = cand.year
        age = max(0, current_year - y_p) if y_p is not None else 3

        sim_scores = cand.similarity_scores or []
        s_max = cand.max_similarity
        s_avg = cand.mean_similarity if cand.mean_similarity > 0 else s_max
        primary_rq = _extract_primary_rq(sim_scores)

        # Archetype 1: Foundational Prior Art Score
        bwd_term = 1.0 if cand.direction in ("backward_reference", "both") else 0.0
        age_maturity = min(1.0, age / 5.0)
        h_foundational = (
            w1 * log_cit_norm
            + w2 * bwd_term
            + w3 * age_maturity
            + w4 * s_avg
        )
        if y_p is not None and y_p <= (current_year - 3):
            h_foundational += 0.10
        if cand.direction == "backward_reference":
            h_foundational += 0.05

        # Archetype 2: Contemporary Breakthrough Score
        recency = max(0.0, 1.0 - (age / 3.0))
        h_contemporary = (
            mu1 * s_max
            + mu2 * recency
            + mu3 * log_cit_norm
        )
        if y_p is not None and y_p >= (current_year - 2) and s_max >= 0.60:
            h_contemporary += 0.15
        elif y_p is not None and y_p >= (current_year - 2):
            h_contemporary += 0.05

        # Archetype 3: Topological Bridge Score
        pr_norm = min(1.0, cand.pagerank_score / max_pagerank) if max_pagerank > 0 else 0.5
        deg_norm = min(1.0, cand.in_graph_degree / max_degree) if max_degree > 0 else 0.5

        if len(sim_scores) >= 2:
            num_scores = [float(s.get("score", 0.0)) for s in sim_scores]
            spread = max(num_scores) - min(num_scores)
            balance = max(0.0, 1.0 - spread)
            min_score = min(num_scores)
            max_score = max(num_scores)
            ratio = (min_score / max_score) if max_score > 0 else 1.0
            multi_rq_balance = 0.6 * balance + 0.4 * ratio
        else:
            multi_rq_balance = 0.5

        h_bridge = (
            gamma1 * pr_norm
            + gamma2 * deg_norm
            + gamma3 * multi_rq_balance
        )
        if cand.in_graph_degree > 1 or cand.pagerank_score > 0.0:
            h_bridge += 0.05

        scores_dict = {
            "foundational": round(float(h_foundational), 4),
            "contemporary": round(float(h_contemporary), 4),
            "bridge": round(float(h_bridge), 4),
        }

        # Candidate clone / copy with updated fields
        cand_dict = cand.model_dump()
        cand_dict["archetype_scores"] = scores_dict
        cand_dict["primary_rq"] = primary_rq

        # Determine partition from highest archetype score
        best_archetype_key = max(scores_dict, key=scores_dict.get)  # type: ignore[arg-type]
        partition_name_map = {
            "foundational": "foundational_prior_art",
            "contemporary": "contemporary_breakthroughs",
            "bridge": "topological_bridges",
        }
        partition_name = partition_name_map[best_archetype_key]
        cand_dict["partition"] = partition_name

        evaluated_cand = CandidatePaperState(**cand_dict)
        evaluated_cand.recommendation_rationale = _generate_candidate_rationale(
            evaluated_cand, partition_name, current_year=current_year
        )
        evaluated_candidates.append(evaluated_cand)

    # 3. Partition grouping
    foundational_list = [
        c for c in evaluated_candidates if c.partition == "foundational_prior_art"
    ]
    contemporary_list = [
        c for c in evaluated_candidates if c.partition == "contemporary_breakthroughs"
    ]
    bridge_list = [
        c for c in evaluated_candidates if c.partition == "topological_bridges"
    ]

    # 4. Partition sorting
    foundational_list.sort(
        key=lambda c: (
            -c.archetype_scores.get("foundational", 0.0),
            -c.citation_count,
            -c.max_similarity,
        )
    )
    contemporary_list.sort(
        key=lambda c: (
            -c.archetype_scores.get("contemporary", 0.0),
            -c.max_similarity,
            -(c.year if c.year is not None else 0),
        )
    )
    bridge_list.sort(
        key=lambda c: (
            -c.archetype_scores.get("bridge", 0.0),
            -c.in_graph_degree,
            -c.pagerank_score,
            -c.max_similarity,
        )
    )

    # 5. Fallback balancing: If a partition is empty but candidate pool has papers,
    # select the highest-scoring candidate for that archetype from the remaining candidates.
    all_sorted_by_foundational = sorted(
        evaluated_candidates,
        key=lambda c: (-c.archetype_scores.get("foundational", 0.0), -c.citation_count),
    )
    all_sorted_by_contemporary = sorted(
        evaluated_candidates,
        key=lambda c: (-c.archetype_scores.get("contemporary", 0.0), -c.max_similarity),
    )
    all_sorted_by_bridge = sorted(
        evaluated_candidates,
        key=lambda c: (-c.archetype_scores.get("bridge", 0.0), -c.in_graph_degree),
    )

    top_foundational = foundational_list[0] if foundational_list else all_sorted_by_foundational[0]
    top_contemporary = contemporary_list[0] if contemporary_list else all_sorted_by_contemporary[0]
    top_bridge = bridge_list[0] if bridge_list else all_sorted_by_bridge[0]

    # 6. Formulate 4 structured SteeringActionOption items
    steering_options: list[SteeringActionOption] = []

    # Option A (Foundational Deep-Dive)
    opt_a_label = f"Expand 1 Hop on Foundational Art ({top_foundational.doi})"
    opt_a_rationale = (
        f"Deep dive into foundational theoretical roots and citation lineage "
        f"of '{top_foundational.title}' ({top_foundational.year or 'undated'})."
    )
    steering_options.append(
        SteeringActionOption(
            option_id="option_a_foundational",
            action_type="expand_deeper",
            target_doi=top_foundational.doi,
            target_title=top_foundational.title,
            label=opt_a_label,
            rationale=opt_a_rationale,
        )
    )

    # Option B (Contemporary Deep-Dive)
    opt_b_label = f"Expand 1 Hop on Contemporary Breakthrough ({top_contemporary.doi})"
    opt_b_rationale = (
        f"Explore cutting-edge empirical advances and benchmark extensions "
        f"of '{top_contemporary.title}' ({top_contemporary.year or 'undated'})."
    )
    steering_options.append(
        SteeringActionOption(
            option_id="option_b_contemporary",
            action_type="expand_deeper",
            target_doi=top_contemporary.doi,
            target_title=top_contemporary.title,
            label=opt_b_label,
            rationale=opt_b_rationale,
        )
    )

    # Option C (Bridge Deep-Dive)
    opt_c_label = f"Expand 1 Hop on Topological Bridge ({top_bridge.doi})"
    opt_c_rationale = (
        f"Traverse high-centrality structural bridge '{top_bridge.title}' "
        f"to uncover cross-cutting papers connecting multiple research questions."
    )
    steering_options.append(
        SteeringActionOption(
            option_id="option_c_bridge",
            action_type="expand_deeper",
            target_doi=top_bridge.doi,
            target_title=top_bridge.title,
            label=opt_c_label,
            rationale=opt_c_rationale,
        )
    )

    # Option D (Adopt & Finalize)
    steering_options.append(
        SteeringActionOption(
            option_id="option_d_adopt_finalize",
            action_type="add_to_library",
            target_doi=None,
            target_title=None,
            label="Add Top Candidates to Project Library & Conclude Cycle",
            rationale=(
                f"Adopt top discovered papers into permanent project library "
                f"and finalize this 1-hop traversal cycle."
            ),
        )
    )

    # 7. Synthesize Strategic Recommendation text
    rec_lines = [
        f"### 🎯 Strategic Traversal Appraisal (Seed: `{seed_doi}`)",
        f"Evaluated **{total_discovered} candidate papers** across 3 topological and semantic archetypes:\n",
    ]

    if foundational_list:
        rec_lines.append(f"#### 🏛️ Foundational Prior Art ({len(foundational_list)} papers)")
        for p in foundational_list[:2]:
            rec_lines.append(f"- **[{p.doi}] {p.title}** ({p.year or 'N/A'})")
            rec_lines.append(f"  *Rationale*: {p.recommendation_rationale}")

    if contemporary_list:
        rec_lines.append(f"\n#### ⚡ Contemporary Breakthroughs ({len(contemporary_list)} papers)")
        for p in contemporary_list[:2]:
            rec_lines.append(f"- **[{p.doi}] {p.title}** ({p.year or 'N/A'})")
            rec_lines.append(f"  *Rationale*: {p.recommendation_rationale}")

    if bridge_list:
        rec_lines.append(f"\n#### 🌉 Topological Bridges ({len(bridge_list)} papers)")
        for p in bridge_list[:2]:
            rec_lines.append(f"- **[{p.doi}] {p.title}** ({p.year or 'N/A'})")
            rec_lines.append(f"  *Rationale*: {p.recommendation_rationale}")

    rec_lines.append("\n#### 🧭 Strategic Steering Choices:")
    for opt in steering_options:
        rec_lines.append(f"- **{opt.label}**: {opt.rationale}")

    strategic_recommendation = "\n".join(rec_lines)

    return TraversalAppraisalResult(
        seed_doi=seed_doi,
        seed_title=seed_title,
        cycle_level=one_hop_result.cycle_level,
        total_discovered=total_discovered,
        total_new=one_hop_result.total_new,
        foundational_prior_art=foundational_list,
        contemporary_breakthroughs=contemporary_list,
        topological_bridges=bridge_list,
        strategic_recommendation=strategic_recommendation,
        steering_options=steering_options,
    )
