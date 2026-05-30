"""Ranking service for sorting and filtering papers in ALRS v2."""
from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from models.ranked_paper import GroupedResults, QuestionGroup, RankedPaper

if TYPE_CHECKING:
    from db.neo4j_service import Neo4jService
    from db.mysql_service import MySQLService


class RankingService:
    """Scoring and ranking engine for papers."""

    def __init__(self, neo4j: Neo4jService, mysql: MySQLService) -> None:
        self._neo4j = neo4j
        self._mysql = mysql

    async def rank_papers(
        self,
        session_id: str,
        similarity_weight: float = 0.7,
        pagerank_weight: float = 0.3,
    ) -> GroupedResults:
        """Score papers via hybrid formula, group by research question, and sort descending."""
        session_data = await self._mysql.get_session(session_id)
        if not session_data:
            raise ValueError(f"Session {session_id} not found")

        questions_raw = session_data["research_questions"]
        research_questions: list[str] = (
            json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw
        )
        threshold: float = float(session_data["similarity_threshold"])

        similarities = await self._neo4j.compute_similarities(session_id, threshold)
        pagerank_scores = await self._neo4j.compute_pagerank(session_id)

        best_matches: dict[str, tuple[str, float]] = {}
        for sim in similarities:
            doi = str(sim["doi"])
            question = str(sim["question"])
            score = float(sim["score"])

            if doi not in best_matches or score > best_matches[doi][1]:
                best_matches[doi] = (question, score)

        matched_dois = list(best_matches.keys())
        papers_data: dict[str, dict[str, Any]] = {}
        if matched_dois:
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
            records = await self._neo4j.execute_read(query, {"dois": matched_dois})
            for record in records:
                papers_data[record["doi"]] = record

        grouped_papers: dict[str, list[RankedPaper]] = {q: [] for q in research_questions}

        for doi, (question, similarity) in best_matches.items():
            if question not in grouped_papers:
                grouped_papers[question] = []

            meta = papers_data.get(doi, {})
            pr_score = pagerank_scores.get(doi, 0.0)
            hybrid_score = (similarity_weight * similarity) + (pagerank_weight * pr_score)

            ranked_paper = RankedPaper(
                doi=doi,
                title=meta.get("title", "[unknown]"),
                year=meta.get("year"),
                cited_by_count=meta.get("cited_by_count", 0),
                similarity_score=similarity,
                pagerank_score=pr_score,
                hybrid_score=hybrid_score,
                question_group=question,
                abstract_snippet=meta.get("abstract_snippet"),
                authors=meta.get("authors", []),
            )
            grouped_papers[question].append(ranked_paper)

        groups: list[QuestionGroup] = []
        total_papers = 0

        for question in research_questions:
            papers = grouped_papers[question]
            papers.sort(
                key=lambda x: (
                    -x.hybrid_score,
                    -x.cited_by_count,
                    -(x.year if x.year is not None else 0)
                )
            )

            avg_sim = (
                sum(p.similarity_score for p in papers) / len(papers)
                if papers
                else 0.0
            )

            groups.append(
                QuestionGroup(
                    question=question,
                    papers=papers,
                    avg_similarity=avg_sim,
                    paper_count=len(papers),
                )
            )
            total_papers += len(papers)

        return GroupedResults(
            session_id=session_id,
            groups=groups,
            total_papers=total_papers,
            similarity_threshold=threshold,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
        )
