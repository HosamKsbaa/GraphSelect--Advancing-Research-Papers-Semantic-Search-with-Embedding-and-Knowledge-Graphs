"""Search and question management tools for the Research Agent.

Each function is an async ADK tool that wraps an existing backend service.
``ToolContext`` is auto-injected by ADK when present as the last parameter.
The ``project_id`` is read from ``tool_context.state`` to scope operations.
"""
from __future__ import annotations

import logging
import uuid

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
        # OpenAlex search endpoint with author name as search query
        data = await ServiceRegistry.openalex._request(
            "GET",
            "/works",
            params={
                "filter": f"authorships.author.display_name.search:{author_name}",
                "per_page": min(max_results, 25),
                "select": "doi,title,publication_year,cited_by_count,authorships",
            },
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        papers: list[dict[str, object]] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
            author_names: list[str] = []
            for auth in authorships:
                author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
                name = author_info.get("display_name")
                if name is not None:
                    author_names.append(str(name))
            papers.append({
                "doi": doi_str,
                "title": str(work.get("title", "")),
                "year": work.get("publication_year"),
                "cited_by_count": int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
                "authors": author_names[:5],
            })
        return {"papers": papers, "total_returned": len(papers)}
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
        data = await ServiceRegistry.openalex._request(
            "GET",
            "/works",
            params={
                "filter": f"primary_location.source.display_name.search:{venue_name}",
                "per_page": min(max_results, 25),
                "select": "doi,title,publication_year,cited_by_count,authorships",
                "sort": "cited_by_count:desc",
            },
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        papers: list[dict[str, object]] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
            author_names: list[str] = []
            for auth in authorships:
                author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
                name = author_info.get("display_name")
                if name is not None:
                    author_names.append(str(name))
            papers.append({
                "doi": doi_str,
                "title": str(work.get("title", "")),
                "year": work.get("publication_year"),
                "cited_by_count": int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
                "authors": author_names[:5],
            })
        return {"papers": papers, "total_returned": len(papers)}
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
        # Generate embedding for the question
        embedding = await ServiceRegistry.embedding_provider.embed_query(
            query=question_text,
        )

        # Generate a unique ID for the question
        question_id = str(uuid.uuid4())

        # Store in Neo4j
        result = await ServiceRegistry.neo4j.create_research_question(
            question_id=question_id,
            text=question_text,
            embedding=embedding,
            project_id=project_id,
        )

        return {
            "status": "created",
            "question_id": result.get("question_id", question_id),
            "text": result.get("text", question_text),
            "project_id": project_id,
        }
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
        questions = await ServiceRegistry.neo4j.get_research_questions(project_id)
        return {
            "questions": [
                {"question_id": q.get("question_id"), "text": q.get("text")}
                for q in questions
            ],
            "total": len(questions),
        }
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
