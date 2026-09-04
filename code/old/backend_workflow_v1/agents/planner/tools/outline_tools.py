"""Outline planning tools for the PlannerAgent.

Provides tools to inspect project state, retrieve ranked papers,
and generate structured literature-review outlines using the LLM.

Tools:
    - get_project_summary: overview of papers, questions, gaps
    - get_ranked_papers: hybrid-scored paper list for outline planning
    - generate_outline: LLM-driven outline generation with paper assignments
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_project_id(tool_context: ToolContext | None) -> str | None:
    """Extract project_id from the ADK ToolContext state."""
    if tool_context is None:
        return None
    state = getattr(tool_context, "state", None)
    if state is None:
        return None
    return state.get("project_id")  # type: ignore[union-attr]


# ------------------------------------------------------------------
# T039 – get_project_summary
# ------------------------------------------------------------------

async def get_project_summary(tool_context: ToolContext) -> dict[str, Any]:
    """Get a summary of the project's current state for planning.

    Returns paper_count, question_count, gap_count, has_outline,
    has_drafts, and a list of research question texts. The agent
    should call this first to understand the project before
    generating an outline.

    Returns:
        A dict with keys: project_id, paper_count, question_count,
        gap_count, has_outline, has_drafts, questions.
    """
    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.planning_service
        result = await service.get_project_summary(project_id)

        # Log the action
        if ServiceRegistry.log_service:
            await ServiceRegistry.log_service.log_agent_trace(
                project_id=project_id,
                agent_name="PlannerAgent",
                event_type="tool_call",
                details={"tool": "get_project_summary", "summary": result},
            )

        return result
    except Exception as exc:
        logger.error("get_project_summary failed: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# T041 – get_ranked_papers
# ------------------------------------------------------------------

async def get_ranked_papers(tool_context: ToolContext) -> dict[str, Any]:
    """Retrieve ranked papers for outline generation using hybrid scoring.

    Combines semantic similarity (against research questions) and
    PageRank centrality in the citation graph. Papers are returned
    in descending order of a combined score.

    Returns:
        A dict with key 'papers' containing a list of dicts, each
        with: doi, title, abstract, year, similarity_score,
        pagerank_score, combined_score.
    """
    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        from features.analysis.service import rank_papers as _rank_papers

        result = await _rank_papers(
            project_id=project_id,
            similarity_weight=0.6,
            pagerank_weight=0.4,
            neo4j=ServiceRegistry.neo4j,
        )

        # Re-map keys for backward compatibility with outline planning
        ranked_papers = result.get("ranked_papers", [])
        papers = [
            {
                "doi": p.get("doi", ""),
                "title": p.get("title", ""),
                "abstract": "",  # abstracts not included in rank_papers
                "year": p.get("year"),
                "similarity_score": p.get("similarity_score", 0.0),
                "pagerank_score": p.get("pagerank_score", 0.0),
                "combined_score": p.get("hybrid_score", 0.0),
            }
            for p in ranked_papers
        ]

        if ServiceRegistry.log_service:
            await ServiceRegistry.log_service.log_agent_trace(
                project_id=project_id,
                agent_name="PlannerAgent",
                event_type="tool_call",
                details={"tool": "get_ranked_papers", "paper_count": len(papers)},
            )

        return {"papers": papers}
    except Exception as exc:
        logger.error("get_ranked_papers failed: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# T040 – generate_outline
# ------------------------------------------------------------------

async def generate_outline(
    style: str = "thematic",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Generate a structured literature review outline from the project's
    ranked papers and research questions.

    Uses the LLM to create thematic or chronological sections, each with
    assigned papers and descriptive summaries.  The result is saved to
    ``projects/{project_id}/outlines/outline.json``.

    Args:
        style: Outline style — one of 'thematic', 'chronological', or
               'methodological'.  Defaults to 'thematic'.

    Returns:
        A dict with keys: sections (list of section dicts), narrative_arc,
        style, and saved_path.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.planning_service
        result = await service.generate_outline(
            project_id=project_id,
            style=style,
        )

        if "error" not in result:
            # Store outline in session state for downstream agents
            tool_context.state["outline"] = {
                "sections": result.get("sections", []),
                "narrative_arc": result.get("narrative_arc", ""),
            }

        return result
    except Exception as exc:
        logger.error("generate_outline failed: %s", exc)
        return {"error": str(exc)}
