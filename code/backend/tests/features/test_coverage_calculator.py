"""Unit tests for Research Question Semantic Coverage Calculator (T034).

Verifies:
- Question coverage formula: C(RQ_i) = min(1.0, sum_{cos >= 0.70} cos / 3.0)
- Zero library papers yields C(RQ_i) = 0.0
- 3 qualifying papers with cos = 0.80 yields C(RQ_i) = 0.80
- Cap at 1.0 when raw coverage exceeds 1.0
- Strict threshold boundary (0.699 excluded, 0.700 included)
- Empty/None vectors and invalid k_target handling
- Parameterized Cypher query contract execution with mock Neo4jService
"""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from features.gap_analysis.coverage_calculator import (
    CALCULATE_RQ_COVERAGE_CYPHER,
    DEFAULT_K_TARGET,
    DEFAULT_MIN_RELEVANCE,
    _parse_coverage_record,
    calculate_coverage_from_embeddings,
    calculate_question_coverage,
    compute_cosine_similarity,
    normalize_coverage_score,
)


# ==============================================================================
# 1. Cosine Similarity & Normalization Primitives
# ==============================================================================

def test_cosine_similarity_identical() -> None:
    """Identical vectors must return 1.0."""
    vec = [0.5, 0.5, 0.5, 0.5]
    assert math.isclose(compute_cosine_similarity(vec, vec), 1.0, rel_tol=1e-5)


def test_cosine_similarity_orthogonal() -> None:
    """Orthogonal vectors must return 0.0."""
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    assert math.isclose(compute_cosine_similarity(vec_a, vec_b), 0.0, abs_tol=1e-5)


def test_cosine_similarity_opposing() -> None:
    """Opposing vectors must return -1.0."""
    vec_a = [1.0, 0.0]
    vec_b = [-1.0, 0.0]
    assert math.isclose(compute_cosine_similarity(vec_a, vec_b), -1.0, rel_tol=1e-5)


def test_cosine_similarity_empty_or_mismatched() -> None:
    """Empty or mismatched dimension vectors return 0.0."""
    assert compute_cosine_similarity([], [1.0, 2.0]) == 0.0
    assert compute_cosine_similarity([1.0], None) == 0.0
    assert compute_cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert compute_cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_normalize_coverage_score_cases() -> None:
    """Test normalization score clipping and rounding."""
    assert normalize_coverage_score(0.0, 0) == 0.0
    assert normalize_coverage_score(0.5, 0) == 0.0
    assert normalize_coverage_score(-0.2, 2) == 0.0
    assert normalize_coverage_score(1.45, 4) == 1.0
    assert normalize_coverage_score(0.73333333, 3) == 0.733


# ==============================================================================
# 2. Vector-Based Coverage Score Calculation
# ==============================================================================

def test_coverage_zero_library_papers() -> None:
    """Zero library papers must yield qualifying_count=0 and coverage=0.0."""
    rq_vec = [1.0, 0.0, 0.0]
    count, raw_cov, score = calculate_coverage_from_embeddings(rq_vec, [])
    assert count == 0
    assert raw_cov == 0.0
    assert score == 0.0


def test_coverage_empty_rq_or_invalid_ktarget() -> None:
    """Empty question vector or non-positive k_target yields 0.0."""
    assert calculate_coverage_from_embeddings([], [[1.0, 0.0]]) == (0, 0.0, 0.0)
    assert calculate_coverage_from_embeddings([1.0, 0.0], [[1.0, 0.0]], k_target=0.0) == (0, 0.0, 0.0)
    assert calculate_coverage_from_embeddings([1.0, 0.0], [[1.0, 0.0]], k_target=-1.0) == (0, 0.0, 0.0)


def test_coverage_three_qualifying_papers() -> None:
    """3 qualifying papers with cos=0.80 yields C(RQ_i) = 0.80."""
    rq_vec = [1.0, 0.0]
    # Build vector with cos(p, rq) = 0.80: [cos, sin]
    cos_val = 0.80
    sin_val = math.sqrt(1.0 - cos_val ** 2)
    p_vec = [cos_val, sin_val]

    papers = [p_vec, p_vec, p_vec]
    count, raw_cov, score = calculate_coverage_from_embeddings(rq_vec, papers, min_relevance=0.70, k_target=3.0)

    assert count == 3
    assert math.isclose(raw_cov, 0.80, rel_tol=1e-4)
    assert score == 0.80


def test_coverage_cap_at_one() -> None:
    """Coverage must cap at 1.0 when raw coverage exceeds k_target."""
    rq_vec = [1.0, 0.0]
    # 4 papers with cos=0.90 -> sum=3.6, raw=1.2, score=1.0
    cos_val = 0.90
    sin_val = math.sqrt(1.0 - cos_val ** 2)
    p_vec = [cos_val, sin_val]

    papers = [p_vec, p_vec, p_vec, p_vec]
    count, raw_cov, score = calculate_coverage_from_embeddings(rq_vec, papers, min_relevance=0.70, k_target=3.0)

    assert count == 4
    assert math.isclose(raw_cov, 1.2, rel_tol=1e-4)
    assert score == 1.0


def test_coverage_threshold_boundary_strict() -> None:
    """Strict test on 0.699 (excluded) vs 0.700 (included)."""
    rq_vec = [1.0, 0.0]

    # Vector with cos = 0.699
    cos_below = 0.699
    sin_below = math.sqrt(1.0 - cos_below ** 2)
    p_below = [cos_below, sin_below]

    # Vector with cos = 0.700
    cos_above = 0.700
    sin_above = math.sqrt(1.0 - cos_above ** 2)
    p_above = [cos_above, sin_above]

    # Only p_below: should be excluded
    count_b, raw_b, score_b = calculate_coverage_from_embeddings(rq_vec, [p_below], min_relevance=0.70)
    assert count_b == 0
    assert raw_b == 0.0
    assert score_b == 0.0

    # Only p_above: should be included
    count_a, raw_a, score_a = calculate_coverage_from_embeddings(rq_vec, [p_above], min_relevance=0.70, k_target=3.0)
    assert count_a == 1
    assert math.isclose(raw_a, 0.700 / 3.0, rel_tol=1e-4)
    assert score_a == round(0.700 / 3.0, 3)


def test_coverage_mixed_papers() -> None:
    """Test mix of qualifying and non-qualifying papers."""
    rq_vec = [1.0, 0.0]
    p_high = [1.0, 0.0]  # cos = 1.0 (qualifies)
    p_low = [0.0, 1.0]   # cos = 0.0 (fails threshold)

    count, raw_cov, score = calculate_coverage_from_embeddings(rq_vec, [p_high, p_low], min_relevance=0.70, k_target=3.0)
    assert count == 1
    assert math.isclose(raw_cov, 1.0 / 3.0, rel_tol=1e-4)
    assert score == round(1.0 / 3.0, 3)


# ==============================================================================
# 3. Cypher Query & Neo4j Service Integration
# ==============================================================================

def test_parse_coverage_record_empty() -> None:
    """Empty record list returns zeros."""
    assert _parse_coverage_record([]) == (0, 0.0, 0.0)


def test_parse_coverage_record_populated() -> None:
    """Populated record parses fields correctly."""
    rec = [{"rq_id": "rq-1", "qualifying_count": 2, "raw_coverage": 0.54, "coverage_score": 0.54}]
    assert _parse_coverage_record(rec) == (2, 0.54, 0.54)


def test_cypher_contract_structure() -> None:
    """Verify CALCULATE_RQ_COVERAGE_CYPHER includes required Cypher contract elements."""
    assert "vector.similarity.cosine(p.embedding, rq.embedding)" in CALCULATE_RQ_COVERAGE_CYPHER
    assert "$min_relevance" in CALCULATE_RQ_COVERAGE_CYPHER
    assert "$k_target" in CALCULATE_RQ_COVERAGE_CYPHER
    assert "p.is_stub = false" in CALCULATE_RQ_COVERAGE_CYPHER
    assert "coverage_score" in CALCULATE_RQ_COVERAGE_CYPHER


@pytest.mark.asyncio
async def test_calculate_question_coverage_neo4j_mock() -> None:
    """Verify calculate_question_coverage invokes neo4j.execute_read with proper params."""
    mock_neo4j = MagicMock()
    mock_neo4j.execute_read = AsyncMock(return_value=[
        {"rq_id": "rq-test-1", "qualifying_count": 3, "raw_coverage": 0.85, "coverage_score": 0.85}
    ])

    count, raw_cov, score = await calculate_question_coverage(
        mock_neo4j, project_id="proj-123", rq_id="rq-test-1", min_relevance=0.70, k_target=3.0
    )

    assert count == 3
    assert raw_cov == 0.85
    assert score == 0.85
    mock_neo4j.execute_read.assert_awaited_once_with(
        CALCULATE_RQ_COVERAGE_CYPHER,
        {
            "project_id": "proj-123",
            "rq_id": "rq-test-1",
            "min_relevance": 0.70,
            "k_target": 3.0,
        },
    )


@pytest.mark.asyncio
async def test_calculate_question_coverage_neo4j_none() -> None:
    """None Neo4jService returns zeros without raising."""
    count, raw_cov, score = await calculate_question_coverage(
        None, project_id="proj-123", rq_id="rq-test-1"  # type: ignore[arg-type]
    )
    assert count == 0
    assert raw_cov == 0.0
    assert score == 0.0
