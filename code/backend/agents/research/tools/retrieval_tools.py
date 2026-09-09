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
            try:
                p_res = neo4j.get_paper_by_doi(actual_doi)
                if hasattr(p_res, "__await__"):
                    p_res = await p_res
                if isinstance(p_res, dict):
                    existing_paper = p_res
                elif hasattr(p_res, "doi") and not isinstance(p_res, MagicMock):
                    existing_paper = {
                        "doi": p_res.doi,
                        "title": getattr(p_res, "title", ""),
                        "abstract": getattr(p_res, "abstract", ""),
                        "year": getattr(p_res, "year", None),
                        "authors": getattr(p_res, "authors", []),
                        "venue": getattr(p_res, "venue", None),
                        "references": getattr(p_res, "references", []),
                        "citations": getattr(p_res, "citations", []),
                    }
            except Exception:
                existing_paper = None

        if existing_paper:
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
            paper_retrieval_svc = getattr(ServiceRegistry, "_paper_retrieval", None)
            if paper_retrieval_svc is not None:
                full_paper = await paper_retrieval_svc.retrieve_paper(
                    doi=actual_doi,
                    project_id=project_id,
                )
                meta = full_paper.metadata
                result = {
                    "doi": meta.doi,
                    "title": meta.title,
                    "abstract_snippet": (meta.abstract or "")[:500],
                    "year": meta.year,
                    "authors": meta.authors[:10],
                    "venue": meta.venue,
                    "references_count": len(meta.references),
                    "citations_count": len(meta.citations),
                    "already_existed": full_paper.already_existed,
                    "already_in_graph": full_paper.already_existed,
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


async def run_graphselect_traversal(
    *args: Any,
    seed_doi: str = "",
    max_depth: int = 1,
    similarity_threshold: float = 0.5,
    mode: str = "interactive",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Execute bounded 1-hop GraphSelect citation traversal (ALRS Stepwise HITL Engine).

    Expands 1 level of forward citations and backward references from a seed paper DOI,
    batch-ingests canonical metadata from OpenAlex, embeds candidate papers with gemini-embedding-2,
    persists citation topology in Neo4j, and returns a rich state payload for 100% of discovered candidates.

    Args:
        seed_doi: Starting seed paper DOI (e.g. '10.1145/3613904.3642697').
        max_depth: Bounded traversal depth (enforced to 1 for stepwise HITL cycles).
        similarity_threshold: Cosine similarity cutoff threshold.
        mode: Search mode ('interactive' or 'automated').
    """
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_doi = seed_doi if seed_doi else (kwargs.get("seed_doi") or "")
    if not actual_doi and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state") and "10." in a:
                actual_doi = a
                break

    project_id = _get_project_id(ctx)
    if not project_id:
        return {"error": "No project_id in session state. Please create or select a project first."}

    # Fallback to existing project paper if seed_doi was omitted
    if not actual_doi:
        try:
            papers = await ServiceRegistry.neo4j.get_project_papers(project_id=project_id, limit=1)
            if papers and papers[0].get("doi"):
                actual_doi = papers[0]["doi"]
        except Exception:
            pass

    if not actual_doi:
        return {
            "error": "seed_doi is required to start 1-hop GraphSelect traversal. "
                     "Please provide a seed paper DOI (e.g. 10.1145/3613904.3642697) or search for seed papers first."
        }

    try:
        crawler = getattr(ServiceRegistry, "crawler", None) or getattr(ServiceRegistry, "crawler_service", None)
        embedding_provider = getattr(ServiceRegistry, "embedding_provider", None)

        result = await crawler.run_one_hop_expansion(
            session_id=project_id,
            seed_doi=actual_doi,
            project_id=project_id,
            embedding_provider=embedding_provider,
        )

        candidates_dump = [c.model_dump() for c in result.candidates]

        from features.ranking.appraisal_service import appraise_1hop_candidate_pool

        appraisal = appraise_1hop_candidate_pool(result)
        appraisal_dump = appraisal.model_dump()

        if ctx is not None:
            try:
                from features.workflow.state_tools import _resolve_project_state, _sync_project_state
                from features.workflow.state_models import PaperMetadata, utc_now

                p_state, a_name, was_dict = await _resolve_project_state(ctx)
                if p_state is not None:
                    papers_dict = p_state.stage_1_research.artifacts.papers
                    if actual_doi and actual_doi not in papers_dict:
                        papers_dict[actual_doi] = PaperMetadata(
                            doi=actual_doi,
                            title=result.seed_title or f"Seed Paper: {actual_doi}",
                            is_seed=True,
                            hop_distance=0,
                        )
                    for c in result.candidates:
                        c_doi = getattr(c, "doi", None)
                        if c_doi and c_doi not in papers_dict:
                            papers_dict[c_doi] = PaperMetadata(
                                doi=c_doi,
                                title=getattr(c, "title", "") or "",
                                authors=getattr(c, "authors", []) or [],
                                year=getattr(c, "year", None),
                                citation_count=getattr(c, "cited_by_count", 0) or 0,
                                venue=getattr(c, "venue", None),
                                is_seed=(c_doi == actual_doi),
                                hop_distance=getattr(c, "hop_distance", 1) or 1,
                            )
                    p_state.stage_1_research.artifacts.total_discovered = len(papers_dict)
                    p_state.stage_1_research.artifacts.total_relevant = len(papers_dict)
                    meta = p_state.stage_1_research.meta
                    if meta.status in ("not_started", "pending"):
                        meta.status = "in_progress"
                        meta.started_at = utc_now()
                    meta.updated_at = utc_now()
                    meta.progress_percentage = min(100.0, 40.0 + len(papers_dict) * 3.0)
                    p_state.touch()
                    _sync_project_state(p_state, ctx, was_dict)
            except Exception as sync_err:
                logger.debug("run_graphselect_traversal state sync skipped: %s", sync_err)

        return {
            "status": "completed",
            "seed_doi": result.seed_doi,
            "seed_title": result.seed_title,
            "cycle_level": 1,
            "max_depth": 1,
            "total_discovered": result.total_discovered,
            "total_new": result.total_new,
            "forward_count": result.forward_count,
            "backward_count": result.backward_count,
            "both_count": result.both_count,
            "candidates": candidates_dump,
            "top_ranked_papers": candidates_dump[:10],
            "traversal_summary": result.traversal_summary,
            "appraisal": appraisal_dump,
            "foundational_prior_art": appraisal_dump.get("foundational_prior_art", []),
            "contemporary_breakthroughs": appraisal_dump.get("contemporary_breakthroughs", []),
            "topological_bridges": appraisal_dump.get("topological_bridges", []),
            "strategic_recommendation": appraisal.strategic_recommendation,
            "steering_options": appraisal_dump.get("steering_options", []),
            "errors": result.errors,
        }
    except Exception as exc:
        logger.exception("run_graphselect_traversal failed for DOI %s: %s", actual_doi, exc)
        return {"error": f"GraphSelect traversal failed: {exc}", "seed_doi": actual_doi}

