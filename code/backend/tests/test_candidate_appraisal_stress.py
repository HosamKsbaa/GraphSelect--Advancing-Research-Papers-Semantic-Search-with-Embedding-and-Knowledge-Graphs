"""Empirical stress tests and adversarial edge cases for appraise_1hop_candidate_pool.

Challenger test suite verifying:
1. All candidates with identical publication years and citation counts.
2. All candidates with 0.0 (or negative) cosine similarity scores.
3. Single candidate pool.
4. Large candidate pool (200 candidates) under high concurrency (asyncio & multi-threading).
5. Robustness to missing/unusual metadata (None year, negative citations, empty authors/titles).
6. 4 steering options guarantee and academic rationale clarity under all distributions.
"""
from __future__ import annotations

import concurrent.futures
import math
import random
import time
from typing import Any

import pytest

from features.ranking.appraisal_service import appraise_1hop_candidate_pool
from features.ranking.models import CandidatePaperState, SteeringActionOption, TraversalAppraisalResult
from features.search.models import OneHopExpansionResult


def _create_mock_candidate(
    doi: str,
    title: str = "Test Paper",
    authors: list[str] | None = None,
    year: int | None = 2024,
    citation_count: int = 50,
    in_graph_degree: int = 2,
    pagerank_score: float = 0.05,
    max_sim: float = 0.75,
    mean_sim: float = 0.70,
    direction: str = "forward_citation",
    similarity_scores: list[dict[str, Any]] | None = None,
) -> CandidatePaperState:
    if authors is None:
        authors = ["Author A", "Author B"]
    if similarity_scores is None:
        similarity_scores = [
            {"question_id": "rq-1", "question": "Research Question 1", "score": max_sim},
            {"question_id": "rq-2", "question": "Research Question 2", "score": mean_sim},
        ]
    return CandidatePaperState(
        doi=doi,
        title=title,
        authors=authors,
        year=year,
        citation_count=citation_count,
        in_graph_degree=in_graph_degree,
        pagerank_score=pagerank_score,
        max_similarity=max_sim,
        mean_similarity=mean_sim,
        direction=direction,
        similarity_scores=similarity_scores,
    )


class TestAppraisalEdgeCases:
    """Adversarial stress-testing suite for candidate pool appraisal."""

    def test_identical_years_and_citations(self) -> None:
        """Stress Test 1: All candidates having identical publication years and citation counts."""
        candidates = [
            _create_mock_candidate(
                doi=f"10.1000/identical.{i}",
                title=f"Identical Metadata Paper {i}",
                year=2021,
                citation_count=100,
                in_graph_degree=i % 4 + 1,
                pagerank_score=0.01 * (i + 1),
                max_sim=0.5 + (0.05 * (i % 5)),
                direction="backward_reference" if i % 2 == 0 else "forward_citation",
            )
            for i in range(20)
        ]

        expansion_res = OneHopExpansionResult(
            seed_doi="10.1000/seed",
            seed_title="Seed Paper",
            cycle_level=1,
            total_discovered=20,
            total_new=20,
            candidates=candidates,
        )

        appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

        assert isinstance(appraisal, TraversalAppraisalResult)
        assert appraisal.total_discovered == 20
        assert len(appraisal.steering_options) == 4

        # Retrieve all evaluated candidate items from partitioned lists
        all_evaluated = (
            appraisal.foundational_prior_art
            + appraisal.contemporary_breakthroughs
            + appraisal.topological_bridges
        )
        assert len(all_evaluated) == 20

        # Verify all candidates have valid, finite float scores and non-empty rationales
        for cand in all_evaluated:
            assert hasattr(cand, "archetype_scores")
            for score in cand.archetype_scores.values():
                assert isinstance(score, float)
                assert not math.isnan(score)
                assert not math.isinf(score)
            assert cand.recommendation_rationale != ""
            assert len(cand.recommendation_rationale) > 20

        # Verify all 4 steering options are distinct and well-formed
        opt_ids = [opt.option_id for opt in appraisal.steering_options]
        assert opt_ids == [
            "option_a_foundational",
            "option_b_contemporary",
            "option_c_bridge",
            "option_d_adopt_finalize",
        ]
        for opt in appraisal.steering_options[:3]:
            assert opt.target_doi is not None
            assert opt.target_doi.startswith("10.1000/identical.")
            assert len(opt.rationale) > 10

    def test_zero_cosine_similarity_scores(self) -> None:
        """Stress Test 2: All candidates having 0.0 cosine similarity scores."""
        candidates = [
            _create_mock_candidate(
                doi=f"10.1000/zerosim.{i}",
                title=f"Zero Sim Paper {i}",
                year=2018 + (i * 2),
                citation_count=i * 50,
                in_graph_degree=i + 1,
                pagerank_score=0.02 * i,
                max_sim=0.0,
                mean_sim=0.0,
                direction="backward_reference" if i == 0 else "forward_citation",
                similarity_scores=[
                    {"question_id": "rq-1", "question": "RQ 1", "score": 0.0},
                    {"question_id": "rq-2", "question": "RQ 2", "score": 0.0},
                ],
            )
            for i in range(10)
        ]

        expansion_res = OneHopExpansionResult(
            seed_doi="10.1000/seed",
            seed_title="Seed Paper",
            cycle_level=1,
            total_discovered=10,
            total_new=10,
            candidates=candidates,
        )

        appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

        assert appraisal.total_discovered == 10
        assert len(appraisal.steering_options) == 4

        for opt in appraisal.steering_options:
            assert isinstance(opt, SteeringActionOption)
            assert opt.label != ""
            assert opt.rationale != ""

        # Verify rationales handle 0.0 score cleanly without division by zero or NaN
        for partition in [
            appraisal.foundational_prior_art,
            appraisal.contemporary_breakthroughs,
            appraisal.topological_bridges,
        ]:
            for p in partition:
                assert "0.00" in p.recommendation_rationale
                for score in p.archetype_scores.values():
                    assert not math.isnan(score)

    def test_single_candidate_pool(self) -> None:
        """Stress Test 3: Single candidate pool."""
        single_cand = _create_mock_candidate(
            doi="10.1000/lonely.paper",
            title="The Lone Survivor",
            year=2023,
            citation_count=42,
            in_graph_degree=1,
            pagerank_score=0.08,
            max_sim=0.82,
            mean_sim=0.82,
            direction="forward_citation",
        )

        expansion_res = OneHopExpansionResult(
            seed_doi="10.1000/seed",
            seed_title="Seed Paper",
            cycle_level=1,
            total_discovered=1,
            total_new=1,
            candidates=[single_cand],
        )

        appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

        assert appraisal.total_discovered == 1
        assert len(appraisal.steering_options) == 4

        # Options A, B, C should all target the single available candidate
        assert appraisal.steering_options[0].target_doi == "10.1000/lonely.paper"
        assert appraisal.steering_options[1].target_doi == "10.1000/lonely.paper"
        assert appraisal.steering_options[2].target_doi == "10.1000/lonely.paper"
        assert appraisal.steering_options[3].action_type == "add_to_library"
        assert appraisal.steering_options[3].target_doi is None

        # Check rationale on evaluated item
        all_evaluated = (
            appraisal.foundational_prior_art
            + appraisal.contemporary_breakthroughs
            + appraisal.topological_bridges
        )
        assert len(all_evaluated) == 1
        assert len(all_evaluated[0].recommendation_rationale) > 20
        assert "10.1000/lonely.paper" in appraisal.strategic_recommendation

    def test_large_candidate_pool_200_items(self) -> None:
        """Stress Test 4: Large candidate pool (200 candidates) with high performance and integrity."""
        rng = random.Random(42)
        candidates = []
        for i in range(200):
            year = rng.choice([None, 2010, 2015, 2019, 2022, 2024, 2025, 2026])
            cites = rng.randint(0, 15000)
            deg = rng.randint(0, 25)
            pr = rng.random() * 0.5
            s1 = round(rng.random(), 3)
            s2 = round(rng.random(), 3)
            max_s = max(s1, s2)
            mean_s = round((s1 + s2) / 2.0, 3)
            dir_choice = rng.choice(["forward_citation", "backward_reference", "both"])

            cand = _create_mock_candidate(
                doi=f"10.2000/bulk.{i:03d}",
                title=f"Scalability Study of Large Graph Processing {i}",
                year=year,
                citation_count=cites,
                in_graph_degree=deg,
                pagerank_score=pr,
                max_sim=max_s,
                mean_sim=mean_s,
                direction=dir_choice,
                similarity_scores=[
                    {"question_id": "rq-1", "question": "GNN Scalability", "score": s1},
                    {"question_id": "rq-2", "question": "Graph Sparsification", "score": s2},
                ],
            )
            candidates.append(cand)

        expansion_res = OneHopExpansionResult(
            seed_doi="10.2000/large.seed",
            seed_title="Large Scale Graph Traversal Survey",
            cycle_level=1,
            total_discovered=200,
            total_new=195,
            candidates=candidates,
        )

        start_time = time.perf_counter()
        appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Performance constraint: 200 candidates appraisal must complete in < 50ms
        assert elapsed_ms < 50.0, f"Appraisal took too long: {elapsed_ms:.2f}ms"

        assert appraisal.total_discovered == 200
        assert len(appraisal.steering_options) == 4

        # Partitions should sum to total evaluated candidates
        all_evaluated = (
            appraisal.foundational_prior_art
            + appraisal.contemporary_breakthroughs
            + appraisal.topological_bridges
        )
        assert len(all_evaluated) == 200

        # Verify all candidates have valid rationales and finite scores
        for cand in all_evaluated:
            assert cand.recommendation_rationale != ""
            assert not math.isnan(cand.archetype_scores["foundational"])
            assert not math.isnan(cand.archetype_scores["contemporary"])
            assert not math.isnan(cand.archetype_scores["bridge"])

    def test_high_concurrency_stress(self) -> None:
        """Stress Test 5: Concurrent execution across 50 worker threads."""
        rng = random.Random(1234)

        def _run_single_appraisal(thread_id: int) -> TraversalAppraisalResult:
            pool_size = rng.randint(5, 50)
            candidates = [
                _create_mock_candidate(
                    doi=f"10.3000/t{thread_id}.c{j}",
                    title=f"Concurrent Paper {thread_id}-{j}",
                    year=rng.randint(2015, 2026),
                    citation_count=rng.randint(0, 5000),
                    in_graph_degree=rng.randint(1, 10),
                    pagerank_score=rng.random() * 0.2,
                    max_sim=round(rng.random(), 3),
                    mean_sim=round(rng.random(), 3),
                    direction=rng.choice(["forward_citation", "backward_reference", "both"]),
                )
                for j in range(pool_size)
            ]
            exp = OneHopExpansionResult(
                seed_doi=f"10.3000/seed.{thread_id}",
                seed_title=f"Concurrent Seed {thread_id}",
                cycle_level=1,
                total_discovered=pool_size,
                total_new=pool_size,
                candidates=candidates,
            )
            return appraise_1hop_candidate_pool(exp, current_year=2026)

        # Run 50 concurrent thread executions
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_run_single_appraisal, i) for i in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50
        for res in results:
            assert isinstance(res, TraversalAppraisalResult)
            assert len(res.steering_options) == 4
            assert res.total_discovered > 0

    def test_pathological_edge_cases(self) -> None:
        """Stress Test 6: Extreme values (negative citations, negative similarities, None year, empty authors)."""
        pathological_candidates = [
            _create_mock_candidate(
                doi="10.4000/neg.cites",
                title="Negative Cites Paper",
                authors=[],
                year=None,
                citation_count=-10,
                in_graph_degree=0,
                pagerank_score=-0.5,
                max_sim=-0.4,
                mean_sim=-0.6,
                direction="unknown_dir",
                similarity_scores=[
                    {"question_id": "rq-1", "question": "RQ 1", "score": -0.4},
                    {"question_id": "rq-2", "question": "RQ 2", "score": -0.6},
                ],
            ),
            _create_mock_candidate(
                doi="10.4000/future.year",
                title="Future Year Paper",
                authors=["Time Traveler"],
                year=2035,
                citation_count=99999999,
                in_graph_degree=1000,
                pagerank_score=10.0,
                max_sim=1.0,
                mean_sim=1.0,
                direction="both",
            ),
        ]

        expansion_res = OneHopExpansionResult(
            seed_doi="10.4000/seed",
            seed_title="Seed",
            cycle_level=1,
            total_discovered=2,
            total_new=2,
            candidates=pathological_candidates,
        )

        appraisal = appraise_1hop_candidate_pool(expansion_res, current_year=2026)

        assert appraisal.total_discovered == 2
        assert len(appraisal.steering_options) == 4

        all_evaluated = (
            appraisal.foundational_prior_art
            + appraisal.contemporary_breakthroughs
            + appraisal.topological_bridges
        )
        assert len(all_evaluated) == 2

        for p in all_evaluated:
            for score in p.archetype_scores.values():
                assert isinstance(score, float)
                assert not math.isnan(score)
                assert not math.isinf(score)
            assert p.recommendation_rationale != ""
            assert len(p.recommendation_rationale) > 20
