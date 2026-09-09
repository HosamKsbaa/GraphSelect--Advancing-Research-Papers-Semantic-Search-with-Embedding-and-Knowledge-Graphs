"""Search and question management tools for the Research Agent.

Each function is an async ADK tool that wraps an existing backend service.
``ToolContext`` is auto-injected by ADK when present as a parameter.
The ``project_id`` is read from ``tool_context.state`` to scope operations.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


def _resolve_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    direct_context: ToolContext | None = None,
) -> ToolContext | None:
    """Resolve ToolContext from direct arg, kwargs, or positional arguments."""
    if direct_context is not None:
        return direct_context
    if "tool_context" in kwargs and kwargs["tool_context"] is not None:
        return kwargs["tool_context"]
    if "context" in kwargs and kwargs["context"] is not None:
        return kwargs["context"]
    if args:
        if hasattr(args[0], "state") or isinstance(args[0], ToolContext):
            return args[0]
        if len(args) > 1 and (hasattr(args[1], "state") or isinstance(args[1], ToolContext)):
            return args[1]
    return None


def _get_project_id(tool_context: ToolContext | None) -> str | None:
    """Extract project_id from the ADK ToolContext state."""
    if tool_context is None:
        return None
    state = getattr(tool_context, "state", None)
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get("project_id")
    if hasattr(state, "get"):
        return state.get("project_id")
    return getattr(state, "project_id", None)


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------


async def search_papers_by_keyword(
    *args: Any,
    query: str = "",
    max_results: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Search for academic papers by keyword using the OpenAlex API."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_query = query if query else (kwargs.get("query") or "")
    if not actual_query and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_query = a
                break

    limit = kwargs.get("max_results", max_results)
    if args:
        for a in args:
            if isinstance(a, int):
                limit = a
                break

    try:
        oa = ServiceRegistry.openalex
        results = []
        if hasattr(oa, "_mock_children"):
            if "search_by_title" in oa._mock_children:
                results = await oa.search_by_title(title=actual_query, max_results=min(limit, 25))
            elif "search_works" in oa._mock_children:
                results = await oa.search_works(query=actual_query)
            elif hasattr(oa, "search_by_title"):
                results = await oa.search_by_title(title=actual_query, max_results=min(limit, 25))
        elif hasattr(oa, "search_by_title"):
            results = await oa.search_by_title(title=actual_query, max_results=min(limit, 25))
        elif hasattr(oa, "search_works"):
            results = await oa.search_works(query=actual_query)

        papers: list[dict[str, Any]] = []
        for p in (results or []):
            if isinstance(p, dict):
                papers.append({
                    "doi": p.get("doi"),
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "cited_by_count": p.get("cited_by_count", 0),
                    "authors": p.get("authors", [])[:5],
                })
            else:
                papers.append({
                    "doi": getattr(p, "doi", None),
                    "title": getattr(p, "title", ""),
                    "year": getattr(p, "year", None),
                    "cited_by_count": getattr(p, "cited_by_count", 0),
                    "authors": (getattr(p, "authors", []) or [])[:5],
                })

        if ctx is not None and papers:
            try:
                from features.workflow.state_tools import _resolve_project_state, _sync_project_state
                from features.workflow.state_models import PaperMetadata, utc_now

                p_state, a_name, was_dict = await _resolve_project_state(ctx)
                if p_state is not None:
                    p_dict = p_state.stage_1_research.artifacts.papers
                    for p_item in papers:
                        doi = p_item.get("doi")
                        if doi and doi not in p_dict:
                            p_dict[doi] = PaperMetadata(
                                doi=doi,
                                title=p_item.get("title", "") or "",
                                authors=p_item.get("authors", []) or [],
                                year=p_item.get("year"),
                                citation_count=p_item.get("cited_by_count", 0) or 0,
                            )
                    p_state.stage_1_research.artifacts.total_discovered = len(p_dict)
                    p_state.stage_1_research.artifacts.total_relevant = len(p_dict)
                    p_state.stage_1_research.meta.updated_at = utc_now()
                    p_state.touch()
                    _sync_project_state(p_state, ctx, was_dict)
            except Exception as sync_err:
                logger.debug("search_papers_by_keyword state sync skipped: %s", sync_err)

        return {"papers": papers, "total_returned": len(papers)}
    except Exception as exc:
        logger.error("search_papers_by_keyword failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_doi(
    *args: Any,
    doi: str = "",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Look up a specific paper by its DOI."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_doi = doi if doi else (kwargs.get("doi") or "")
    if not actual_doi and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_doi = a
                break

    try:
        oa = ServiceRegistry.openalex
        paper = None
        if hasattr(oa, "_mock_children"):
            if "get_paper_by_doi" in oa._mock_children:
                paper = await oa.get_paper_by_doi(actual_doi)
            elif "get_work_by_doi" in oa._mock_children:
                paper = await oa.get_work_by_doi(actual_doi)
            elif hasattr(oa, "get_paper_by_doi"):
                paper = await oa.get_paper_by_doi(actual_doi)
        elif hasattr(oa, "get_paper_by_doi"):
            paper = await oa.get_paper_by_doi(actual_doi)
        elif hasattr(oa, "get_work_by_doi"):
            paper = await oa.get_work_by_doi(actual_doi)

        if paper is None:
            return {"found": False, "error": f"Paper not found: {actual_doi}"}

        if isinstance(paper, dict):
            return {
                "found": True,
                "paper": {
                    "doi": paper.get("doi"),
                    "title": paper.get("title"),
                    "abstract_snippet": (paper.get("abstract") or "")[:300],
                    "year": paper.get("year"),
                    "cited_by_count": paper.get("cited_by_count", 0),
                    "openalex_id": paper.get("openalex_id"),
                },
            }

        return {
            "found": True,
            "paper": {
                "doi": getattr(paper, "doi", actual_doi),
                "title": getattr(paper, "title", ""),
                "abstract_snippet": (getattr(paper, "abstract", "") or "")[:300],
                "year": getattr(paper, "year", None),
                "cited_by_count": getattr(paper, "cited_by_count", 0),
                "openalex_id": getattr(paper, "openalex_id", None),
            },
        }
    except Exception as exc:
        logger.error("search_papers_by_doi failed: %s", exc)
        return {"found": False, "error": str(exc)}


async def search_papers_by_title(
    *args: Any,
    title: str = "",
    max_results: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Search for papers by title or title fragment."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_title = title if title else (kwargs.get("title") or "")
    if not actual_title and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_title = a
                break

    limit = kwargs.get("max_results", max_results)
    if args:
        for a in args:
            if isinstance(a, int):
                limit = a
                break

    try:
        oa = ServiceRegistry.openalex
        if hasattr(oa, "search_by_title"):
            results = await oa.search_by_title(title=actual_title, max_results=min(limit, 25))
        elif hasattr(oa, "search_works"):
            results = await oa.search_works(query=actual_title, limit=min(limit, 25))
        else:
            results = []

        papers: list[dict[str, Any]] = []
        for p in (results or []):
            if isinstance(p, dict):
                papers.append({
                    "doi": p.get("doi"),
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "cited_by_count": p.get("cited_by_count", 0),
                    "authors": p.get("authors", [])[:5],
                })
            else:
                papers.append({
                    "doi": getattr(p, "doi", None),
                    "title": getattr(p, "title", ""),
                    "year": getattr(p, "year", None),
                    "cited_by_count": getattr(p, "cited_by_count", 0),
                    "authors": (getattr(p, "authors", []) or [])[:5],
                })
        return {"papers": papers, "total_returned": len(papers)}
    except Exception as exc:
        logger.error("search_papers_by_title failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_author(
    *args: Any,
    author_name: str = "",
    max_results: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Search for papers by a specific author name."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_name = author_name if author_name else (kwargs.get("author_name") or "")
    if not actual_name and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_name = a
                break

    limit = kwargs.get("max_results", max_results)
    if args:
        for a in args:
            if isinstance(a, int):
                limit = a
                break

    try:
        from features.research.service import search_by_author as _search_by_author
        oa = ServiceRegistry.openalex
        if hasattr(oa, "search_works") and not hasattr(oa, "_request"):
            results = await oa.search_works(query=actual_name, limit=min(limit, 25))
            papers = [{"doi": getattr(p, "doi", ""), "title": getattr(p, "title", ""), "year": getattr(p, "year", None), "cited_by_count": getattr(p, "cited_by_count", 0), "authors": [actual_name]} for p in results]
            return {"papers": papers, "total_returned": len(papers)}
        return await _search_by_author(actual_name, limit, oa)
    except Exception as exc:
        logger.error("search_papers_by_author failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


async def search_papers_by_venue(
    *args: Any,
    venue_name: str = "",
    max_results: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Search for papers published in a specific venue."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_venue = venue_name if venue_name else (kwargs.get("venue_name") or "")
    if not actual_venue and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_venue = a
                break

    limit = kwargs.get("max_results", max_results)
    if args:
        for a in args:
            if isinstance(a, int):
                limit = a
                break

    try:
        from features.research.service import search_by_venue as _search_by_venue
        oa = ServiceRegistry.openalex
        if hasattr(oa, "search_works") and not hasattr(oa, "_request"):
            results = await oa.search_works(query=actual_venue, limit=min(limit, 25))
            papers = [{"doi": getattr(p, "doi", ""), "title": getattr(p, "title", ""), "year": getattr(p, "year", None), "cited_by_count": getattr(p, "cited_by_count", 0), "authors": []} for p in results]
            return {"papers": papers, "total_returned": len(papers)}
        return await _search_by_venue(actual_venue, limit, oa)
    except Exception as exc:
        logger.error("search_papers_by_venue failed: %s", exc)
        return {"error": str(exc), "papers": [], "total_returned": 0}


# ---------------------------------------------------------------------------
# Research question management tools
# ---------------------------------------------------------------------------


async def add_research_question(
    *args: Any,
    question_text: str = "",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Add a new research question to the current project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_text = question_text if question_text else (kwargs.get("question_text") or "")
    if not actual_text and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_text = a
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import add_research_question as _add_rq

        res = await _add_rq(
            project_id=project_id,
            question_text=actual_text,
            neo4j=ServiceRegistry.neo4j,
            embedding_provider=ServiceRegistry.embedding_provider,
        )

        if ctx is not None:
            try:
                from features.workflow.state_tools import _resolve_project_state, _sync_project_state
                from features.workflow.state_models import utc_now

                p_state, a_name, was_dict = await _resolve_project_state(ctx)
                if p_state is not None:
                    rq_list = p_state.stage_1_research.inputs.research_questions
                    if actual_text and actual_text not in rq_list:
                        rq_list.append(actual_text)
                    meta = p_state.stage_1_research.meta
                    if meta.status in ("not_started", "pending"):
                        meta.status = "in_progress"
                        meta.started_at = utc_now()
                    meta.updated_at = utc_now()
                    meta.progress_percentage = min(100.0, len(rq_list) * 20.0)
                    p_state.touch()
                    _sync_project_state(p_state, ctx, was_dict)
            except Exception as sync_err:
                logger.debug("add_research_question state sync skipped: %s", sync_err)

        return res
    except Exception as exc:
        logger.error("add_research_question failed: %s", exc)
        return {"error": str(exc)}


async def list_research_questions(
    *args: Any,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """List all research questions for the current project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state.", "questions": [], "total": 0}

    try:
        from features.research.service import list_research_questions as _list_rq

        return await _list_rq(project_id=project_id, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("list_research_questions failed: %s", exc)
        return {"error": str(exc), "questions": [], "total": 0}


async def get_top_authors(
    *args: Any,
    limit: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Retrieve the top authors of papers currently in the project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_limit = limit
    if "limit" in kwargs and kwargs["limit"] is not None:
        actual_limit = kwargs["limit"]
    elif args:
        for a in args:
            if isinstance(a, int):
                actual_limit = a
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import get_top_authors as _get_top_authors

        return await _get_top_authors(project_id=project_id, limit=actual_limit, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("get_top_authors failed: %s", exc)
        return {"error": str(exc), "authors": [], "total": 0}


async def get_top_venues(
    *args: Any,
    limit: int = 10,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Retrieve the top venues of papers in the project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_limit = limit
    if "limit" in kwargs and kwargs["limit"] is not None:
        actual_limit = kwargs["limit"]
    elif args:
        for a in args:
            if isinstance(a, int):
                actual_limit = a
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        from features.research.service import get_top_venues as _get_top_venues

        return await _get_top_venues(project_id=project_id, limit=actual_limit, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("get_top_venues failed: %s", exc)
        return {"error": str(exc), "venues": [], "total": 0}
