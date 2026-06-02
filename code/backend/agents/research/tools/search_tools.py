"""Search and question management tools for the Research Agent.

Each function is an async ADK tool that wraps an existing backend service.
``ToolContext`` is auto-injected by ADK when present as the last parameter.
The ``project_id`` is read from ``tool_context.state`` to scope operations.
"""
from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------


async def search_papers_by_keyword(
    query: str,
    max_results: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Search for academic papers by keyword using the OpenAlex API.

    Use this tool when you need to find papers related to a broad topic
    or set of keywords.  Returns a list of candidate papers with basic
    metadata.

    Args:
        query: Keywords or phrases to search for (e.g. "graph neural networks").
        max_results: Maximum number of results to return (1-25, default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - papers: list of {doi, title, year, cited_by_count, authors}
          - total_returned: int — number of papers in this response
    """
    try:
        results = await ServiceRegistry.openalex.search_by_title(
            title=query,
            max_results=min(max_results, 25),
        )
        papers = [
            {
                "doi": p.doi,
                "title": p.title,
                "year": p.year,
                "cited_by_count": p.cited_by_count,
                "authors": p.authors[:5],
            }
            for p in results
        ]
        return {"papers": papers, "total_returned": len(papers)}
    except Exception as exc:
        logger.error("search_papers_by_keyword failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_doi(
    doi: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Look up a specific paper by its DOI.

    Use this tool when you have an exact DOI and need the paper's
    metadata from OpenAlex.

    Args:
        doi: The DOI of the paper (e.g. "10.1145/3292500.3330919").
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with the paper metadata or an error message.
    """
    try:
        paper = await ServiceRegistry.openalex.get_paper_by_doi(doi)
        if paper is None:
            return {"found": False, "error": f"Paper not found: {doi}"}
        return {
            "found": True,
            "paper": {
                "doi": paper.doi,
                "title": paper.title,
                "abstract_snippet": (paper.abstract or "")[:300],
                "year": paper.year,
                "cited_by_count": paper.cited_by_count,
                "openalex_id": paper.openalex_id,
            },
        }
    except Exception as exc:
        logger.error("search_papers_by_doi failed: %s", exc)
        return {"found": False, "error": str(exc)}


async def search_papers_by_title(
    title: str,
    max_results: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Search for papers by title or title fragment.

    Useful when you know part of a paper's title and want to find exact
    matches or close variants.

    Args:
        title: Full or partial paper title to search for.
        max_results: Maximum number of results to return (1-25, default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - papers: list of {doi, title, year, cited_by_count, authors}
          - total_returned: int
    """
    try:
        results = await ServiceRegistry.openalex.search_by_title(
            title=title,
            max_results=min(max_results, 25),
        )
        papers = [
            {
                "doi": p.doi,
                "title": p.title,
                "year": p.year,
                "cited_by_count": p.cited_by_count,
                "authors": p.authors[:5],
            }
            for p in results
        ]
        return {"papers": papers, "total_returned": len(papers)}
    except Exception as exc:
        logger.error("search_papers_by_title failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_author(
    author_name: str,
    max_results: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Search for papers by a specific author name.

    Use this when the user asks about a particular researcher's work.
    Searches OpenAlex with the author name as a filter.

    Args:
        author_name: Full or partial author name (e.g. "Yoshua Bengio").
        max_results: Maximum number of results (1-25, default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - papers: list of {doi, title, year, cited_by_count, authors}
          - total_returned: int
    """
    try:
        from features.research.service import search_by_author as _search_by_author

        return await _search_by_author(author_name, max_results, ServiceRegistry.openalex)
    except Exception as exc:
        logger.error("search_papers_by_author failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_venue(
    venue_name: str,
    max_results: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Search for papers published in a specific venue (journal/conference).

    Use this when the user asks about papers from a specific venue like
    "NeurIPS", "Nature", or "ACL".

    Args:
        venue_name: Name of the venue/journal/conference.
        max_results: Maximum number of results (1-25, default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - papers: list of {doi, title, year, cited_by_count, authors}
          - total_returned: int
    """
    try:
        from features.research.service import search_by_venue as _search_by_venue

        return await _search_by_venue(venue_name, max_results, ServiceRegistry.openalex)
    except Exception as exc:
        logger.error("search_papers_by_venue failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


# ---------------------------------------------------------------------------
# Research question management tools
# ---------------------------------------------------------------------------


async def add_research_question(
    question_text: str,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Add a new research question to the current project.

    Embeds the question text using the configured embedding provider and
    stores it in Neo4j linked to the project.  Research questions are used
    to compute relevance scores for discovered papers.

    Args:
        question_text: The research question text (e.g.
            "How do graph neural networks handle heterogeneous graphs?").
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with the created question details or an error.
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import add_research_question as _add_rq

        return await _add_rq(
            project_id=project_id,
            question_text=question_text,
            neo4j=ServiceRegistry.neo4j,
            embedding_provider=ServiceRegistry.embedding_provider,
        )
    except Exception as exc:
        logger.error("add_research_question failed: %s", exc)
        return {"error": str(exc)}


async def list_research_questions(
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """List all research questions for the current project.

    Returns the questions that have been defined for this project.
    These questions are used to score paper relevance.

    Args:
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - questions: list of {question_id, text}
          - total: int — number of questions
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state.", "questions": [], "total": 0}

    try:
        from features.research.service import list_research_questions as _list_rq

        return await _list_rq(project_id=project_id, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("list_research_questions failed: %s", exc)
        return {"error": str(exc), "questions": [], "total": 0}


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


async def get_top_authors(
    limit: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Retrieve the top authors of papers currently in the project.

    Queries the Neo4j citation graph to find the authors that appear most
    frequently on papers added to the project.

    Args:
        limit: Maximum number of authors to return (default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - authors: list of {name, openalex_id, paper_count}
          - total: int — total unique authors found
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import get_top_authors as _get_top_authors

        return await _get_top_authors(project_id=project_id, limit=limit, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("get_top_authors failed: %s", exc)
        return {"error": str(exc), "authors": [], "total": 0}


async def get_top_venues(
    limit: int = 10,
    tool_context: ToolContext | None = None,
) -> dict[str, object]:
    """Retrieve the top venues (journals/conferences) of papers in the project.

    Queries the Neo4j citation graph to find the venues that have published
    the most papers currently in the project.

    Args:
        limit: Maximum number of venues to return (default 10).
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with keys:
          - venues: list of {name, openalex_id, paper_count}
          - total: int — total unique venues found
    """
    project_id = _get_project_id(tool_context)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import get_top_venues as _get_top_venues

        return await _get_top_venues(project_id=project_id, limit=limit, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("get_top_venues failed: %s", exc)
        return {"error": str(exc), "venues": [], "total": 0}
