"""Analysis and gap-finding tools for the Gap Finder Agent.

These tools compute similarity scores, analyze coverage gaps, generate
search queries for uncovered areas, and produce hybrid paper rankings.
"""
from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

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
        from features.analysis.service import compute_paper_similarity

        return await compute_paper_similarity(
            project_id=project_id, doi=doi, neo4j=ServiceRegistry.neo4j,
        )
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
        from features.analysis.service import get_citation_stats as _get_citation_stats

        return await _get_citation_stats(project_id=project_id, neo4j=ServiceRegistry.neo4j)
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
        from features.analysis.service import analyze_coverage as _analyze_coverage

        return await _analyze_coverage(
            project_id=project_id, threshold=threshold, neo4j=ServiceRegistry.neo4j,
        )
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
        from features.analysis.service import suggest_gap_queries as _suggest_gap_queries

        return await _suggest_gap_queries(
            gap_question=gap_question,
            max_queries=5,
            llm=ServiceRegistry.llm,
        )
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
        from features.analysis.service import rank_papers as _rank_papers

        return await _rank_papers(
            project_id=project_id,
            similarity_weight=similarity_weight,
            pagerank_weight=pagerank_weight,
            neo4j=ServiceRegistry.neo4j,
        )
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
