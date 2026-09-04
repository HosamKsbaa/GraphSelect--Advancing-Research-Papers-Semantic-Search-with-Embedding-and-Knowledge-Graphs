"""Review tool for the ReviewerAgent.

Provides a tool that evaluates a drafted section for accuracy,
completeness, citation coverage, and coherence using the LLM.

Tools:
    - review_section: LLM-driven section review with structured feedback
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
# T046 – review_section
# ------------------------------------------------------------------

async def review_section(
    section_title: str,
    draft_markdown: str,
    assigned_dois: list[str],
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Review a drafted section for accuracy, completeness, and coherence.

    Evaluates the section against academic standards, checking citation
    coverage, logical flow, synthesis quality, and factual consistency
    with the source papers.

    Args:
        section_title: Title of the section being reviewed.
        draft_markdown: The full Markdown text of the draft.
        assigned_dois: List of DOIs that should be cited in this section.

    Returns:
        A dict with keys:
        - approved (bool): True if the section meets quality standards.
        - feedback (list[str]): Specific improvement suggestions.
        - missing_citations (list[str]): DOIs assigned but not cited.
        - scores (dict): Sub-scores for coverage, coherence, synthesis.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id = _get_project_id(tool_context) or ""

    try:
        service = ServiceRegistry.writing_service
        review_data = await service.review_section(
            project_id=project_id,
            section_title=section_title,
            draft_text=draft_markdown,
            paper_dois=assigned_dois,
        )

        # Store review result in session state
        tool_context.state["last_review"] = review_data

        return review_data
    except Exception as exc:
        logger.error("review_section failed: %s", exc)
        return {"error": str(exc)}
