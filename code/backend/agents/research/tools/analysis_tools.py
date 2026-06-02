"""Analysis and gap-finding tools for the Gap Finder Agent.

These tools compute similarity scores, analyze coverage gaps, generate
search queries for uncovered areas, and produce hybrid paper rankings.
"""
from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from core.llm.models import CompletionRequest

logger = logging.getLogger(__name__)


async def compute_similarity(
    doi: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Compute cosine similarity between a paper and all project research questions.

    Uses the Neo4j vector index to efficiently compute similarities between
    the paper's embedding and each research question embedding.

    Args:
        doi: The DOI of the paper to score.
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - doi: the paper DOI
          - scores: list of {question, score} — similarity to each question
          - avg_score: float — average similarity across all questions
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        # Get research questions for the project
        questions = await ServiceRegistry.neo4j.get_research_questions(project_id)
        if not questions:
            return {"doi": doi, "scores": [], "avg_score": 0.0, "note": "No research questions defined."}

        # Get the paper's embedding status
        has_emb = await ServiceRegistry.neo4j.has_embedding(doi)
        if not has_emb:
            return {
                "doi": doi,
                "scores": [],
                "avg_score": 0.0,
                "note": "Paper has no embedding. Use explore_paper first.",
            }

        # Compute similarities using Neo4j vector index
        similarities = await ServiceRegistry.neo4j.compute_similarities(
            session_id=project_id,
            threshold=0.0,
            top_k=100,
        )

        # Filter for this DOI
        paper_scores = [
            {"question": s.get("question", ""), "score": round(float(s.get("score", 0)), 4)}
            for s in similarities
            if s.get("doi") == doi
        ]

        avg_score = 0.0
        if paper_scores:
            avg_score = round(sum(s["score"] for s in paper_scores) / len(paper_scores), 4)  # type: ignore[arg-type]

        return {"doi": doi, "scores": paper_scores, "avg_score": avg_score}

    except Exception as exc:
        logger.error("compute_similarity failed for %s: %s", doi, exc)
        return {"error": str(exc), "doi": doi}


async def get_citation_stats(
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Get aggregate citation and similarity statistics for the project.

    Provides an overview of the project's paper library including total
    papers, citation counts, and average similarity per research question.

    Args:
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - total_papers: int
          - total_citations: int — sum of cited_by_count across all papers
          - avg_citations: float — average citations per paper
          - question_coverage: list of {question, avg_similarity, paper_count}
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        # Get all project papers
        papers = await ServiceRegistry.neo4j.get_project_papers(project_id, limit=200)
        total_papers = len(papers)
        total_citations = sum(int(p.get("cited_by_count") or 0) for p in papers)
        avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0.0

        # Get research questions
        questions = await ServiceRegistry.neo4j.get_research_questions(project_id)

        # Compute per-question similarity stats
        question_coverage: list[dict[str, object]] = []
        if questions and total_papers > 0:
            try:
                similarities = await ServiceRegistry.neo4j.compute_similarities(
                    session_id=project_id,
                    threshold=0.0,
                    top_k=500,
                )
                # Group scores by question
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

    except Exception as exc:
        logger.error("get_citation_stats failed: %s", exc)
        return {"error": str(exc)}


async def analyze_coverage(
    threshold: float = 0.6,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Analyze how well the current paper library covers each research question.

    Identifies gaps where research questions lack sufficiently similar papers.
    A question is considered "covered" when at least one paper exceeds the
    similarity threshold.

    Args:
        threshold: Similarity threshold for considering a question covered
            (0.0-1.0, default 0.6).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - overall_coverage: float — fraction of questions adequately covered
          - covered_questions: list of {question, best_score, paper_count}
          - gap_questions: list of {question, best_score, paper_count}
          - recommendation: str — summary of coverage analysis
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        questions = await ServiceRegistry.neo4j.get_research_questions(project_id)
        if not questions:
            return {
                "overall_coverage": 0.0,
                "covered_questions": [],
                "gap_questions": [],
                "recommendation": "No research questions defined. Add questions first.",
            }

        papers = await ServiceRegistry.neo4j.get_project_papers(project_id, limit=200)
        if not papers:
            return {
                "overall_coverage": 0.0,
                "covered_questions": [],
                "gap_questions": [{"question": q.get("text"), "best_score": 0.0, "paper_count": 0} for q in questions],
                "recommendation": "No papers in the project. Start searching for papers.",
            }

        # Compute similarities
        similarities = await ServiceRegistry.neo4j.compute_similarities(
            session_id=project_id,
            threshold=0.0,
            top_k=1000,
        )

        # Group by question
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

    except Exception as exc:
        logger.error("analyze_coverage failed: %s", exc)
        return {"error": str(exc)}


async def suggest_gap_queries(
    gap_question: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Generate search queries to find papers that fill a coverage gap.

    Uses the LLM to analyze a poorly-covered research question and suggest
    specific search queries that are likely to find relevant papers.

    Args:
        gap_question: The research question text that lacks sufficient coverage.
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - gap_question: the original question
          - suggested_queries: list of search query strings
    """
    try:
        prompt = f"""You are a research assistant helping find academic papers.

The following research question is not well-covered by the current paper library:

"{gap_question}"

Generate 5 specific and diverse search queries that would help find papers
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

        response = await ServiceRegistry.llm.complete(request)
        raw = response.text.strip()

        # Parse JSON array
        import json
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
            "suggested_queries": queries[:7],
        }

    except Exception as exc:
        logger.error("suggest_gap_queries failed: %s", exc)
        return {
            "error": str(exc),
            "gap_question": gap_question,
            "suggested_queries": [],
        }


async def rank_papers(
    similarity_weight: float = 0.7,
    pagerank_weight: float = 0.3,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Rank project papers using a hybrid score combining similarity and PageRank.

    Produces a ranked list of papers that balances topical relevance
    (similarity to research questions) with citation importance (PageRank
    in the citation graph).

    Args:
        similarity_weight: Weight for similarity score (0.0-1.0, default 0.7).
        pagerank_weight: Weight for PageRank score (0.0-1.0, default 0.3).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - ranked_papers: list of {doi, title, similarity_score,
            pagerank_score, hybrid_score, year}
          - total: int — number of ranked papers
          - weights: {similarity, pagerank} — the weights used
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        # Get project papers
        papers = await ServiceRegistry.neo4j.get_project_papers(project_id, limit=200)
        if not papers:
            return {"ranked_papers": [], "total": 0, "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight}}

        # Build DOI -> paper map
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
            similarities = await ServiceRegistry.neo4j.compute_similarities(
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
            pr_scores = await ServiceRegistry.neo4j.compute_pagerank(
                session_id=project_id,
            )
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

        # Sort by hybrid score descending
        ranked.sort(key=lambda x: float(x.get("hybrid_score", 0)), reverse=True)  # type: ignore[arg-type]

        return {
            "ranked_papers": ranked,
            "total": len(ranked),
            "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight},
        }

    except Exception as exc:
        logger.error("rank_papers failed: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_id(tool_context: ToolContext | None) -> str | None:
    """Extract project_id from the ADK ToolContext state.

    Args:
        tool_context: The ADK ToolContext (may be None in tests).

    Returns:
        The project_id string or None if not available.
    """
    if tool_context is None:
        return None
    state = getattr(tool_context, "state", None)
    if state is None:
        return None
    return state.get("project_id")  # type: ignore[union-attr]
