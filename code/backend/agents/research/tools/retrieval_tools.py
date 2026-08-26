"""Paper retrieval and library management tools for the Research Agent.

These tools handle exploring individual papers in depth (with similarity
scoring) and managing the project's paper library.
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


async def explore_paper(
    *args: Any,
    doi: str = "",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Retrieve full details of a paper and score it against project questions."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_doi = doi if doi else (kwargs.get("doi") or "")
    if not actual_doi and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_doi = a
                break

    project_id = _get_project_id(ctx)

    try:
        neo4j = ServiceRegistry.neo4j
        existing_paper = None
        if hasattr(neo4j, "get_paper_by_doi"):
            existing_paper = await neo4j.get_paper_by_doi(actual_doi)

        if hasattr(ServiceRegistry, "paper_retrieval") and ServiceRegistry.paper_retrieval:
            full_paper = await ServiceRegistry.paper_retrieval.retrieve_paper(
                doi=actual_doi,
                project_id=project_id,
            )
            meta = full_paper.metadata
            already_existed = full_paper.already_existed or (existing_paper is not None)
            result: dict[str, object] = {
                "doi": meta.doi,
                "title": meta.title,
                "abstract_snippet": (meta.abstract or "")[:500],
                "year": meta.year,
                "authors": meta.authors[:10],
                "venue": meta.venue,
                "references_count": len(meta.references),
                "citations_count": len(meta.citations),
                "already_existed": already_existed,
                "already_in_graph": already_existed,
            }
        elif existing_paper:
            result = {
                "doi": existing_paper.get("doi", actual_doi),
                "title": existing_paper.get("title", ""),
                "abstract_snippet": (existing_paper.get("abstract") or "")[:500],
                "year": existing_paper.get("year"),
                "authors": existing_paper.get("authors", [])[:10],
                "venue": existing_paper.get("venue"),
                "references_count": len(existing_paper.get("references", [])),
                "citations_count": len(existing_paper.get("citations", [])),
                "already_existed": True,
                "already_in_graph": True,
            }
        else:
            result = {
                "doi": actual_doi,
                "title": "",
                "abstract_snippet": "",
                "year": None,
                "authors": [],
                "venue": None,
                "references_count": 0,
                "citations_count": 0,
                "already_existed": False,
                "already_in_graph": False,
            }

        if project_id and neo4j:
            try:
                questions = await neo4j.get_research_questions(project_id)
                if questions:
                    similarities = await neo4j.compute_similarities(
                        session_id=project_id,
                        threshold=0.0,
                        top_k=10,
                    )
                    paper_scores = [
                        {"question": s.get("question", ""), "score": round(float(s.get("score", 0)), 4)}
                        for s in (similarities or [])
                        if s.get("doi") == actual_doi
                    ]
                    result["similarity_scores"] = paper_scores
            except Exception as sim_exc:
                logger.warning("Similarity computation failed for %s: %s", actual_doi, sim_exc)
                result["similarity_scores"] = []

        return result

    except ValueError as ve:
        return {"error": str(ve), "doi": actual_doi}
    except Exception as exc:
        logger.error("explore_paper failed for %s: %s", actual_doi, exc)
        return {"error": str(exc), "doi": actual_doi}


async def add_paper_to_project(
    *args: Any,
    doi: str = "",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Add a paper to the current project's library."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_doi = doi if doi else (kwargs.get("doi") or "")
    if not actual_doi and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_doi = a
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state. Create or select a project first."}

    try:
        neo4j = ServiceRegistry.neo4j
        if hasattr(neo4j, "add_paper_to_project"):
            await neo4j.add_paper_to_project(project_id=project_id, doi=actual_doi)

        if hasattr(ServiceRegistry, "paper_retrieval") and ServiceRegistry.paper_retrieval:
            full_paper = await ServiceRegistry.paper_retrieval.retrieve_paper(
                doi=actual_doi,
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

        return {
            "status": "added",
            "doi": actual_doi,
            "title": f"Paper {actual_doi}",
            "year": None,
            "already_existed": False,
            "embedded": True,
        }
    except ValueError as ve:
        return {"error": str(ve), "doi": actual_doi}
    except Exception as exc:
        logger.error("add_paper_to_project failed for %s: %s", actual_doi, exc)
        return {"error": str(exc), "doi": actual_doi}


async def get_project_papers(
    *args: Any,
    sort_by: str = "relevance",
    limit: int = 50,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Get all papers in the current project's library."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_sort = kwargs.get("sort_by", sort_by)
    actual_limit = kwargs.get("limit", limit)
    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state.", "papers": [], "total": 0}

    try:
        papers = await ServiceRegistry.neo4j.get_project_papers(
            project_id=project_id,
            limit=actual_limit,
        )

        if actual_sort == "year" and papers:
            papers.sort(key=lambda p: p.get("year") or 0, reverse=True)
        elif actual_sort == "citations" and papers:
            papers.sort(key=lambda p: p.get("cited_by_count") or 0, reverse=True)

        formatted_papers = [
            {
                "doi": p.get("doi"),
                "title": p.get("title"),
                "year": p.get("year"),
                "cited_by_count": p.get("cited_by_count"),
                "abstract_snippet": (p.get("abstract") or "")[:200],
            }
            for p in (papers or [])
        ]

        return {"papers": formatted_papers, "total": len(formatted_papers)}
    except Exception as exc:
        logger.error("get_project_papers failed: %s", exc)
        return {"error": str(exc), "papers": [], "total": 0}
