"""Analysis domain service — pure business logic, no ADK or FastAPI deps.

Functions in this module are the single source of truth for:
  - paper similarity scoring
  - citation statistics
  - coverage gap analysis
  - LLM-driven gap-query suggestions
  - hybrid (similarity + PageRank) paper ranking
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paper similarity
# ---------------------------------------------------------------------------


async def compute_paper_similarity(
    project_id: str,
    doi: str,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Compute cosine similarity between a paper and all project research questions.

    Returns:
        ``{doi, scores: [{question, score}], avg_score: float}``
    """
    questions = await neo4j.get_research_questions(project_id)
    if not questions:
        return {"doi": doi, "scores": [], "avg_score": 0.0, "note": "No research questions defined."}

    has_emb = await neo4j.has_embedding(doi)
    if not has_emb:
        return {
            "doi": doi,
            "scores": [],
            "avg_score": 0.0,
            "note": "Paper has no embedding. Use explore_paper first.",
        }

    similarities = await neo4j.compute_similarities(
        session_id=project_id,
        threshold=0.0,
        top_k=100,
    )

    paper_scores = [
        {"question": s.get("question", ""), "score": round(float(s.get("score", 0)), 4)}
        for s in similarities
        if s.get("doi") == doi
    ]

    avg_score = 0.0
    if paper_scores:
        avg_score = round(sum(s["score"] for s in paper_scores) / len(paper_scores), 4)  # type: ignore[arg-type]

    return {"doi": doi, "scores": paper_scores, "avg_score": avg_score}


# ---------------------------------------------------------------------------
# Citation statistics
# ---------------------------------------------------------------------------


async def get_citation_stats(
    project_id: str,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Aggregate citation and similarity statistics for the project.

    Returns:
        ``{total_papers, total_citations, avg_citations, question_coverage: [...]}``
    """
    papers = await neo4j.get_project_papers(project_id, limit=200)
    total_papers = len(papers)
    total_citations = sum(int(p.get("cited_by_count") or 0) for p in papers)
    avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0.0

    questions = await neo4j.get_research_questions(project_id)

    question_coverage: list[dict[str, object]] = []
    if questions and total_papers > 0:
        try:
            similarities = await neo4j.compute_similarities(
                session_id=project_id,
                threshold=0.0,
                top_k=500,
            )
            q_scores: dict[str, list[float]] = {}
            for s in similarities:
                q_text = str(s.get("question", ""))
                score = float(s.get("score", 0))
                if q_text not in q_scores:
                    q_scores[q_text] = []
                q_scores[q_text].append(score)

            for q in questions:
                q_text = str(q.get("text", ""))
                scores = q_scores.get(q_text, [])
                question_coverage.append({
                    "question": q_text,
                    "avg_similarity": round(sum(scores) / len(scores), 4) if scores else 0.0,
                    "paper_count": len(scores),
                })
        except Exception as sim_exc:
            logger.warning("Similarity stats failed: %s", sim_exc)

    return {
        "total_papers": total_papers,
        "total_citations": total_citations,
        "avg_citations": avg_citations,
        "question_coverage": question_coverage,
    }


# ---------------------------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------------------------


async def analyze_coverage(
    project_id: str,
    threshold: float,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Analyse how well the paper library covers each research question.

    Returns:
        ``{overall_coverage, covered_questions, gap_questions, recommendation}``
    """
    questions = await neo4j.get_research_questions(project_id)
    if not questions:
        return {
            "overall_coverage": 0.0,
            "covered_questions": [],
            "gap_questions": [],
            "recommendation": "No research questions defined. Add questions first.",
        }

    papers = await neo4j.get_project_papers(project_id, limit=200)
    if not papers:
        return {
            "overall_coverage": 0.0,
            "covered_questions": [],
            "gap_questions": [{"question": q.get("text"), "best_score": 0.0, "paper_count": 0} for q in questions],
            "recommendation": "No papers in the project. Start searching for papers.",
        }

    similarities = await neo4j.compute_similarities(
        session_id=project_id,
        threshold=0.0,
        top_k=1000,
    )

    q_data: dict[str, dict[str, object]] = {}
    for q in questions:
        q_text = str(q.get("text", ""))
        q_data[q_text] = {"best_score": 0.0, "paper_count": 0}

    for s in similarities:
        q_text = str(s.get("question", ""))
        score = float(s.get("score", 0))
        if q_text in q_data:
            q_data[q_text]["paper_count"] = int(q_data[q_text]["paper_count"]) + 1  # type: ignore[arg-type]
            if score > float(q_data[q_text]["best_score"]):  # type: ignore[arg-type]
                q_data[q_text]["best_score"] = score

    covered: list[dict[str, object]] = []
    gaps: list[dict[str, object]] = []
    for q_text, data in q_data.items():
        entry = {
            "question": q_text,
            "best_score": round(float(data["best_score"]), 4),  # type: ignore[arg-type]
            "paper_count": data["paper_count"],
        }
        if float(data["best_score"]) >= threshold:  # type: ignore[arg-type]
            covered.append(entry)
        else:
            gaps.append(entry)

    total_q = len(questions)
    overall = round(len(covered) / total_q, 4) if total_q > 0 else 0.0

    if not gaps:
        recommendation = "All research questions are well-covered! Consider refining questions or exploring niche subtopics."
    elif overall >= 0.5:
        recommendation = f"{len(gaps)} of {total_q} questions have gaps. Focus searches on: {', '.join(g['question'][:60] + '...' for g in gaps[:3])}"  # type: ignore[index]
    else:
        recommendation = f"Major coverage gaps detected ({len(gaps)} of {total_q} questions). Prioritize broader searches to build the paper library."

    return {
        "overall_coverage": overall,
        "covered_questions": covered,
        "gap_questions": gaps,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Gap-query suggestion (LLM)
# ---------------------------------------------------------------------------


async def suggest_gap_queries(
    gap_question: str,
    max_queries: int,
    llm: LLMService,
) -> dict[str, Any]:
    """Use the LLM to generate search queries that fill a coverage gap.

    Returns:
        ``{gap_question, suggested_queries: [str, ...]}``
    """
    from core.llm.models import CompletionRequest

    prompt = f"""You are a research assistant helping find academic papers.

The following research question is not well-covered by the current paper library:

"{gap_question}"

Generate {max_queries} specific and diverse search queries that would help find papers
relevant to this question. Each query should target a different angle or
subtopic. Return ONLY a JSON array of strings.

Example output: ["query 1", "query 2", "query 3", "query 4", "query 5"]
"""
    request = CompletionRequest(
        prompt=prompt,
        system_instruction="You are an academic research assistant. Respond with valid JSON only.",
        temperature=0.7,
        max_tokens=512,
        response_format="application/json",
    )

    response = await llm.complete(request)
    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    queries = json.loads(raw)
    if not isinstance(queries, list):
        queries = [str(queries)]

    return {
        "gap_question": gap_question,
        "suggested_queries": queries[:max_queries],
    }


# ---------------------------------------------------------------------------
# Hybrid paper ranking  (similarity × weight + PageRank × weight)
# ---------------------------------------------------------------------------


async def rank_papers(
    project_id: str,
    similarity_weight: float,
    pagerank_weight: float,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Rank project papers with a hybrid score combining similarity and PageRank.

    This single implementation replaces both ``analysis_tools.rank_papers``
    and ``outline_tools.get_ranked_papers``.

    Returns:
        ``{ranked_papers: [...], total: int, weights: {similarity, pagerank}}``
    """
    papers = await neo4j.get_project_papers(project_id, limit=200)
    if not papers:
        return {
            "ranked_papers": [],
            "total": 0,
            "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight},
        }

    # Build DOI → paper map
    doi_map: dict[str, dict[str, object]] = {}
    for p in papers:
        doi = str(p.get("doi", ""))
        doi_map[doi] = {
            "doi": doi,
            "title": p.get("title"),
            "year": p.get("year"),
            "cited_by_count": p.get("cited_by_count"),
        }

    # Compute average similarity per paper
    sim_scores: dict[str, float] = {}
    try:
        similarities = await neo4j.compute_similarities(
            session_id=project_id,
            threshold=0.0,
            top_k=1000,
        )
        doi_sim_list: dict[str, list[float]] = {}
        for s in similarities:
            d = str(s.get("doi", ""))
            if d in doi_map:
                if d not in doi_sim_list:
                    doi_sim_list[d] = []
                doi_sim_list[d].append(float(s.get("score", 0)))
        for d, scores in doi_sim_list.items():
            sim_scores[d] = sum(scores) / len(scores) if scores else 0.0
    except Exception as sim_exc:
        logger.warning("Similarity computation failed in rank_papers: %s", sim_exc)

    # Compute PageRank scores
    pr_scores: dict[str, float] = {}
    try:
        pr_scores = await neo4j.compute_pagerank(session_id=project_id)
    except Exception as pr_exc:
        logger.warning("PageRank computation failed in rank_papers: %s", pr_exc)

    # Compute hybrid scores
    ranked: list[dict[str, object]] = []
    for doi, paper_info in doi_map.items():
        sim = sim_scores.get(doi, 0.0)
        pr = pr_scores.get(doi, 0.0)
        hybrid = round(similarity_weight * sim + pagerank_weight * pr, 4)
        ranked.append({
            "doi": doi,
            "title": paper_info.get("title"),
            "year": paper_info.get("year"),
            "similarity_score": round(sim, 4),
            "pagerank_score": round(pr, 4),
            "hybrid_score": hybrid,
        })

    ranked.sort(key=lambda x: float(x.get("hybrid_score", 0)), reverse=True)  # type: ignore[arg-type]

    return {
        "ranked_papers": ranked,
        "total": len(ranked),
        "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight},
    }
