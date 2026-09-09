"""Question Semantic Coverage Calculator (T036).

Calculates semantic coverage score C(RQ_i) for active research questions:
    C(RQ_i) = min(1.0, sum_{cos >= min_relevance} cos / k_target)
with default min_relevance = 0.70 and k_target = 3.0.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C8: Pure Neo4j SSOT.
- C9: Granular functions strictly under 25 lines (SRP & SLAP).
- C11: Clear domain naming and predicates.
"""
from __future__ import annotations

import math
from typing import Any

from core.db.neo4j_service import Neo4jService

DEFAULT_MIN_RELEVANCE: float = 0.70
DEFAULT_K_TARGET: float = 3.0

CALCULATE_RQ_COVERAGE_CYPHER: str = (
    "MATCH (proj:Project {project_id: $project_id}) "
    "MATCH (rq:ResearchQuestion {question_id: $rq_id}) "
    "OPTIONAL MATCH (proj)-[:CONTAINS]->(p:Paper) "
    "WHERE p.is_stub = false "
    "  AND p.embedding IS NOT NULL "
    "  AND rq.embedding IS NOT NULL "
    "  AND vector.similarity.cosine(p.embedding, rq.embedding) >= $min_relevance "
    "WITH rq, "
    "     count(p) AS qualifying_count, "
    "     coalesce(sum(vector.similarity.cosine(p.embedding, rq.embedding)), 0.0) AS sim_sum "
    "RETURN "
    "    rq.question_id AS rq_id, "
    "    qualifying_count, "
    "    CASE "
    "        WHEN qualifying_count = 0 THEN 0.0 "
    "        ELSE toFloat(sim_sum) / $k_target "
    "    END AS raw_coverage, "
    "    CASE "
    "        WHEN qualifying_count = 0 THEN 0.0 "
    "        WHEN (toFloat(sim_sum) / $k_target) > 1.0 THEN 1.0 "
    "        ELSE round(toFloat(sim_sum) / $k_target, 3) "
    "    END AS coverage_score;"
)


def compute_cosine_similarity(vec_a: list[float] | None, vec_b: list[float] | None) -> float:
    """Compute mathematical cosine similarity between two float vectors bounded to [-1.0, 1.0]."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    val = dot / (norm_a * norm_b)
    return max(-1.0, min(1.0, float(val)))


def normalize_coverage_score(raw_coverage: float, qualifying_count: int) -> float:
    """Normalize raw coverage to [0.0, 1.0] with 3-decimal rounding."""
    if qualifying_count == 0 or raw_coverage <= 0.0:
        return 0.0
    if raw_coverage > 1.0:
        return 1.0
    return round(raw_coverage, 3)


def calculate_coverage_from_embeddings(
    rq_embedding: list[float],
    paper_embeddings: list[list[float]],
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    k_target: float = DEFAULT_K_TARGET,
) -> tuple[int, float, float]:
    """Calculate semantic question coverage score from raw vectors for offline/unit testing."""
    if not rq_embedding or not paper_embeddings or k_target <= 0.0:
        return 0, 0.0, 0.0
    qualifying_sims = [
        sim for p_emb in paper_embeddings
        if (sim := compute_cosine_similarity(p_emb, rq_embedding)) >= min_relevance
    ]
    count = len(qualifying_sims)
    if count == 0:
        return 0, 0.0, 0.0
    raw_cov = sum(qualifying_sims) / k_target
    score = normalize_coverage_score(raw_cov, count)
    return count, raw_cov, score


def _parse_coverage_record(records: list[dict[str, Any]]) -> tuple[int, float, float]:
    """Extract qualifying count, raw coverage, and score from Cypher record."""
    if not records:
        return 0, 0.0, 0.0
    rec = records[0]
    return (
        int(rec.get("qualifying_count", 0)),
        float(rec.get("raw_coverage", 0.0)),
        float(rec.get("coverage_score", 0.0)),
    )


async def calculate_question_coverage(
    neo4j: Neo4jService,
    project_id: str,
    rq_id: str,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    k_target: float = DEFAULT_K_TARGET,
) -> tuple[int, float, float]:
    """Execute parameterized Neo4j Cypher query to calculate semantic question coverage."""
    if neo4j is None:
        return 0, 0.0, 0.0
    params = {
        "project_id": project_id,
        "rq_id": rq_id,
        "min_relevance": min_relevance,
        "k_target": k_target,
    }
    records = await neo4j.execute_read(CALCULATE_RQ_COVERAGE_CYPHER, params)
    return _parse_coverage_record(records)
