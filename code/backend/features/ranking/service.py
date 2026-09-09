"""Ranking service for sorting and filtering papers in ALRS v2."""
from __future__ import annotations

import json
import math
from typing import Any, TYPE_CHECKING

from features.ranking.models import GroupedResults, QuestionGroup, RankedPaper

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService


def compute_adaptive_threshold(similarity_scores: list[float]) -> float:
    """Compute adaptive quantile threshold tau_t = mu - sigma per Constitution A8."""
    if not similarity_scores:
        return 0.0
    mean_val = sum(similarity_scores) / len(similarity_scores)
    variance = sum((s - mean_val) ** 2 for s in similarity_scores) / len(similarity_scores)
    std_dev = math.sqrt(variance)
    return max(0.0, mean_val - std_dev)


def parse_research_questions(questions_raw: Any) -> list[str]:
    """Parse research questions from JSON string or list."""
    if isinstance(questions_raw, str):
        try:
            return list(json.loads(questions_raw))
        except Exception:
            return [questions_raw]
    return list(questions_raw or [])


def extract_best_similarities(
    similarities: list[dict[str, Any]],
    cutoff_threshold: float = 0.0,
) -> dict[str, tuple[str, float]]:
    """Extract highest similarity score per DOI above cutoff threshold."""
    best_matches: dict[str, tuple[str, float]] = {}
    for sim in similarities:
        score = float(sim.get("score", 0.0))
        if score < cutoff_threshold:
            continue
        doi = str(sim["doi"])
        question = str(sim.get("question", ""))
        if doi not in best_matches or score > best_matches[doi][1]:
            best_matches[doi] = (question, score)
    return best_matches


def build_ranked_paper(
    doi: str,
    question: str,
    similarity: float,
    meta: dict[str, Any],
    pagerank: float,
    similarity_weight: float,
    pagerank_weight: float,
) -> RankedPaper:
    """Build a single RankedPaper instance with computed hybrid score."""
    hybrid_score = (similarity_weight * similarity) + (pagerank_weight * pagerank)
    return RankedPaper(
        doi=doi,
        title=meta.get("title", "[unknown]"),
        year=meta.get("year"),
        cited_by_count=meta.get("cited_by_count") or 0,
        similarity_score=similarity,
        pagerank_score=pagerank,
        hybrid_score=hybrid_score,
        question_group=question,
        abstract_snippet=meta.get("abstract_snippet"),
        authors=meta.get("authors", []),
    )


def assemble_question_groups(
    research_questions: list[str],
    ranked_papers: list[RankedPaper],
) -> tuple[list[QuestionGroup], int]:
    """Group ranked papers by question, sort with tie-breaking, and return totals."""
    grouped_papers: dict[str, list[RankedPaper]] = {q: [] for q in research_questions}
    for paper in ranked_papers:
        if paper.question_group not in grouped_papers:
            grouped_papers[paper.question_group] = []
        grouped_papers[paper.question_group].append(paper)

    groups: list[QuestionGroup] = []
    total_papers = 0
    for question in research_questions:
        papers = grouped_papers[question]
        papers.sort(
            key=lambda x: (-x.hybrid_score, -x.cited_by_count, -(x.year if x.year is not None else 0))
        )
        avg_sim = sum(p.similarity_score for p in papers) / len(papers) if papers else 0.0
        groups.append(
            QuestionGroup(
                question=question,
                papers=papers,
                avg_similarity=avg_sim,
                paper_count=len(papers),
            )
        )
        total_papers += len(papers)
    return groups, total_papers


class RankingService:
    """Scoring and ranking engine for papers backed by Neo4j."""

    def __init__(self, neo4j: Neo4jService, mysql: Any = None) -> None:
        self._neo4j = neo4j
        self._mysql = mysql

    async def _resolve_session_data(self, session_id: str) -> dict[str, Any]:
        """Fetch session metadata from Neo4j :ResearchCampaign or legacy fallback."""
        if hasattr(self._neo4j, "execute_read"):
            try:
                res = await self._neo4j.execute_read(
                    "MATCH (c:ResearchCampaign) "
                    "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
                    "RETURN c LIMIT 1",
                    {"session_id": session_id},
                )
                if isinstance(res, list) and res and isinstance(res[0], dict) and res[0].get("c"):
                    node = res[0].get("c", {})
                    return dict(node) if hasattr(node, "items") else dict(node)
            except Exception:
                pass

        if self._mysql is not None and hasattr(self._mysql, "get_session"):
            legacy = await self._mysql.get_session(session_id)
            if legacy:
                return dict(legacy)
        raise ValueError(f"Session {session_id} not found")


    async def _fetch_papers_data(self, dois: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch metadata for specified DOIs from Neo4j."""
        if not dois:
            return {}
        query = """
        MATCH (p:Paper)
        WHERE p.doi IN $dois
        OPTIONAL MATCH (a:Author)-[r:AUTHORED]->(p)
        WITH p, a ORDER BY r.position
        RETURN p.doi AS doi,
               p.title AS title,
               p.year AS year,
               p.cited_by_count AS cited_by_count,
               substring(p.abstract, 0, 300) AS abstract_snippet,
               collect(a.name) AS authors
        """
        records = await self._neo4j.execute_read(query, {"dois": dois})
        return {r["doi"]: r for r in records}

    async def rank_papers(
        self,
        session_id: str,
        similarity_weight: float = 0.7,
        pagerank_weight: float = 0.3,
        use_adaptive_pruning: bool = False,
    ) -> GroupedResults:
        """Score papers via hybrid formula, group by research question, and sort descending."""
        session_data = await self._resolve_session_data(session_id)
        research_questions = parse_research_questions(session_data.get("research_questions", []))
        base_threshold = float(session_data.get("similarity_threshold", 0.5))

        similarities = await self._neo4j.compute_similarities(session_id, base_threshold)
        pagerank_scores = await self._neo4j.compute_pagerank(session_id)

        cutoff = base_threshold
        if use_adaptive_pruning and similarities:
            all_sims = [float(s.get("score", 0.0)) for s in similarities]
            cutoff = max(cutoff, compute_adaptive_threshold(all_sims))

        best_matches = extract_best_similarities(similarities, cutoff)
        papers_data = await self._fetch_papers_data(list(best_matches.keys()))

        ranked_papers = [
            build_ranked_paper(
                doi, question, sim, papers_data.get(doi, {}),
                pagerank_scores.get(doi, 0.0), similarity_weight, pagerank_weight,
            )
            for doi, (question, sim) in best_matches.items()
        ]

        groups, total_papers = assemble_question_groups(research_questions, ranked_papers)
        return GroupedResults(
            session_id=session_id,
            groups=groups,
            total_papers=total_papers,
            similarity_threshold=cutoff,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
        )
