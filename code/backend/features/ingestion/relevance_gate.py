"""Global relevance gate invariant evaluator (FR-016).

Complies with Constitution v2.2.1:
- C7: Strict static typing.
- C9: Granular functions under 25 lines (SRP / SLAP).
- C11: Intention-revealing domain types and predicate booleans.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RELEVANCE_THRESHOLD: float = 0.75


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


def evaluate_paper_relevance(
    paper_embedding: list[float] | None,
    rq_embeddings: list[list[float]],
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    is_user_override: bool = False,
) -> tuple[bool, float]:
    """Evaluate whether paper passes FR-016 relevance gate to permit deep expansion."""
    if is_user_override:
        max_sim = _calculate_max_similarity(paper_embedding, rq_embeddings)
        return True, max_sim
    if not paper_embedding or not rq_embeddings:
        return False, 0.0
    max_sim = _calculate_max_similarity(paper_embedding, rq_embeddings)
    can_expand = max_sim >= threshold
    return can_expand, max_sim


def _calculate_max_similarity(
    paper_embedding: list[float] | None, rq_embeddings: list[list[float]]
) -> float:
    """Compute maximum cosine similarity across active research question vectors."""
    if not paper_embedding or not rq_embeddings:
        return 0.0
    scores = [compute_cosine_similarity(paper_embedding, rq_emb) for rq_emb in rq_embeddings]
    return max(scores) if scores else 0.0


async def fetch_project_rq_embeddings(neo4j_service: Any, project_id: str) -> list[list[float]]:
    """Retrieve embeddings for active research questions in project from Neo4j."""
    query = """
    MATCH (rq:ResearchQuestion)
    WHERE (rq.project_id = $project_id OR (:Project {project_id: $project_id})-[:HAS_RESEARCH_QUESTION]->(rq))
      AND rq.embedding IS NOT NULL
    RETURN rq.embedding AS embedding
    """
    try:
        records = await neo4j_service.execute_read(query, {"project_id": project_id})
        embeddings: list[list[float]] = []
        for r in records:
            emb = r.get("embedding")
            if isinstance(emb, list) and emb:
                embeddings.append([float(x) for x in emb])
        return embeddings
    except Exception as exc:
        logger.warning("Failed to fetch RQ embeddings for project %s: %s", project_id, exc)
        return []


async def evaluate_paper_for_project(
    neo4j_service: Any,
    project_id: str,
    paper_embedding: list[float] | None,
    is_user_override: bool = False,
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
) -> tuple[bool, float]:
    """Fetch project RQ embeddings and evaluate relevance gate for paper."""
    rq_embeddings = await fetch_project_rq_embeddings(neo4j_service, project_id)
    return evaluate_paper_relevance(
        paper_embedding=paper_embedding,
        rq_embeddings=rq_embeddings,
        threshold=threshold,
        is_user_override=is_user_override,
    )
