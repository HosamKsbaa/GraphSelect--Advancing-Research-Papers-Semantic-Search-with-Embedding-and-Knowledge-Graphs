"""Paper retrieval and library management tools for the Research Agent.

These tools handle exploring individual papers in depth (with similarity
scoring) and managing the project's paper library.
"""
from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


async def explore_paper(
    doi: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Retrieve full details of a paper and score it against project questions.

    Use this tool to deeply explore a paper you found via search.  It will:
    1. Fetch complete metadata from OpenAlex (title, abstract, authors, venue)
    2. Store the paper in the knowledge graph with citation relationships
    3. Embed the abstract for similarity computations
    4. Compute similarity scores against all project research questions
    5. Link the paper to the current project

    Args:
        doi: The DOI of the paper to explore (e.g. "10.1145/3292500.3330919").
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - doi, title, abstract_snippet, year, authors, venue
          - references_count, citations_count
          - similarity_scores: list of {question, score} — how relevant to each RQ
          - already_existed: bool — whether paper was already in the graph
    """
    project_id = _get_project_id(tool_context)

    try:
        full_paper = await ServiceRegistry.paper_retrieval.retrieve_paper(
            doi=doi,
            project_id=project_id,
        )

        meta = full_paper.metadata
        result: dict[str, object] = {
            "doi": meta.doi,
            "title": meta.title,
            "abstract_snippet": (meta.abstract or "")[:500],
            "year": meta.year,
            "authors": meta.authors[:10],
            "venue": meta.venue,
            "references_count": len(meta.references),
            "citations_count": len(meta.citations),
            "already_existed": full_paper.already_existed,
        }

        # Compute similarity scores against project questions if we have a project
        if project_id:
            try:
                questions = await ServiceRegistry.neo4j.get_research_questions(project_id)
                if questions and full_paper.embedding:
                    # Use Neo4j vector similarity via the compute_similarities method
                    # which uses the paper_embeddings ANN index
                    similarities = await ServiceRegistry.neo4j.compute_similarities(
                        session_id=project_id,  # We reuse session_id param for project scope
                        threshold=0.0,  # Get all scores, even low ones
                        top_k=10,
                    )
                    # Filter for this DOI only
                    paper_scores = [
                        {"question": s.get("question", ""), "score": round(float(s.get("score", 0)), 4)}
                        for s in similarities
                        if s.get("doi") == doi
                    ]
                    result["similarity_scores"] = paper_scores
            except Exception as sim_exc:
                logger.warning("Similarity computation failed for %s: %s", doi, sim_exc)
                result["similarity_scores"] = []

        return result

    except ValueError as ve:
        return {"error": str(ve), "doi": doi}
    except Exception as exc:
        logger.error("explore_paper failed for %s: %s", doi, exc)
        return {"error": str(exc), "doi": doi}


async def add_paper_to_project(
    doi: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Add a paper to the current project's library.

    Use this to manually add a paper you've found to the project.
    The paper will be fully retrieved (metadata, embedding, citations)
    and linked to the project in the knowledge graph.

    Args:
        doi: The DOI of the paper to add (e.g. "10.1145/3292500.3330919").
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict indicating success or failure with paper details.
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        full_paper = await ServiceRegistry.paper_retrieval.retrieve_paper(
            doi=doi,
            project_id=project_id,
        )
        meta = full_paper.metadata
        return {
            "status": "added",
            "doi": meta.doi,
            "title": meta.title,
            "year": meta.year,
            "already_existed": full_paper.already_existed,
            "embedded": full_paper.embedding is not None,
        }
    except ValueError as ve:
        return {"error": str(ve), "doi": doi}
    except Exception as exc:
        logger.error("add_paper_to_project failed for %s: %s", doi, exc)
        return {"error": str(exc), "doi": doi}


async def get_project_papers(
    sort_by: str = "relevance",
    limit: int = 50,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Get all papers in the current project's library.

    Returns the papers that have been added to this project, with
    basic metadata.  Use this to review what papers are already
    in the project before searching for more.

    Args:
        sort_by: Sort order — "relevance" (default), "year", or "citations".
        limit: Maximum number of papers to return (default 50).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - papers: list of paper metadata dicts
          - total: int — number of papers in the project
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state.", "papers": [], "total": 0}

    try:
        papers = await ServiceRegistry.neo4j.get_project_papers(
            project_id=project_id,
            limit=limit,
        )

        # Sort based on requested order
        if sort_by == "year" and papers:
            papers.sort(key=lambda p: p.get("year") or 0, reverse=True)
        elif sort_by == "citations" and papers:
            papers.sort(key=lambda p: p.get("cited_by_count") or 0, reverse=True)
        # "relevance" is default graph order

        formatted_papers = [
            {
                "doi": p.get("doi"),
                "title": p.get("title"),
                "year": p.get("year"),
                "cited_by_count": p.get("cited_by_count"),
                "abstract_snippet": (p.get("abstract") or "")[:200],
            }
            for p in papers
        ]

        return {"papers": formatted_papers, "total": len(formatted_papers)}
    except Exception as exc:
        logger.error("get_project_papers failed: %s", exc)
        return {"error": str(exc), "papers": [], "total": 0}


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
