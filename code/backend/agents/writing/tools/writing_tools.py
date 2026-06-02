"""Writing tools for the DraftingAgent.

Provides tools for retrieving paper abstracts and drafting individual
sections of the literature review using the LLM.

Tools:
    - get_paper_abstracts: batch-fetch abstracts by DOI list
    - draft_section: LLM-driven section drafting with citations
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
# T044 – get_paper_abstracts
# ------------------------------------------------------------------

async def get_paper_abstracts(
    dois: list[str],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve abstracts for a list of papers to provide writing context.

    The drafting agent calls this to gather source material before writing
    a section.  Only DOIs that exist in the graph are returned.

    Args:
        dois: List of DOI strings to look up.

    Returns:
        A dict with key 'papers' — a list of dicts each containing
        doi, title, abstract, year, and authors (if available).
    """
    project_id = _get_project_id(tool_context) or ""

    try:
        service = ServiceRegistry.writing_service
        return await service.get_paper_abstracts(project_id, dois)
    except Exception as exc:
        logger.error("get_paper_abstracts failed: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# T045 – draft_section
# ------------------------------------------------------------------

async def draft_section(
    section_title: str,
    section_description: str,
    paper_dois: list[str],
    target_level: str = "master",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Draft a single section of the literature review using the LLM.

    Generates a Markdown section with inline citations in the format
    ``(Author, Year)`` keyed to the provided DOIs.  The draft is
    persisted to ``projects/{project_id}/drafts/{slug}.md``.

    Args:
        section_title: The heading for this section.
        section_description: 2-3 sentence description of the section's scope.
        paper_dois: List of DOIs assigned to this section.
        target_level: Academic level — 'master' or 'phd'.

    Returns:
        A dict with keys: section_title, markdown, word_count,
        cited_dois, saved_path.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.writing_service
        result = await service.draft_section(
            project_id=project_id,
            section_title=section_title,
            section_description=section_description,
            paper_dois=paper_dois,
            target_level=target_level,
        )

        # Store in session state for the reviewer
        if "markdown" in result:
            drafts_state: dict[str, str] = tool_context.state.get("section_drafts", {})
            drafts_state[section_title] = result["markdown"]
            tool_context.state["section_drafts"] = drafts_state

        return result
    except Exception as exc:
        logger.error("draft_section failed: %s", exc)
        return {"error": str(exc)}
