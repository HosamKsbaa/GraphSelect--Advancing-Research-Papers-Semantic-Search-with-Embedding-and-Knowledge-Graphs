"""Export tools for the WriterAgent.

Deterministic (non-LLM) tools that convert the project's paper library
and Markdown drafts into publication-ready BibTeX and LaTeX outputs.

Tools:
    - export_bibtex: Generate a .bib file from project papers
    - export_latex: Convert Markdown drafts into a LaTeX document
    - export_citation_graph: Export citation network as JSON + GraphML
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
# T047 – export_bibtex
# ------------------------------------------------------------------

async def export_bibtex(
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Export the project's paper library as a BibTeX file.

    Queries Neo4j for all papers linked to the project and formats
    them as BibTeX entries.  The resulting ``.bib`` file is saved to
    ``projects/{project_id}/exports/references.bib``.

    Returns:
        A dict with keys: entry_count, saved_path, bibtex_preview
        (first 500 chars of the generated BibTeX).
    """
    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.export_service
        return await service.export_bibtex(project_id)
    except Exception as exc:
        logger.error("export_bibtex failed: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# T048 – export_latex
# ------------------------------------------------------------------

async def export_latex(
    template: str = "ieee",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Convert approved Markdown draft sections into a LaTeX document.

    Reads all ``.md`` files from ``projects/{project_id}/drafts/``,
    converts them to LaTeX using the specified template, generates
    a companion ``.bib`` file, and saves both to
    ``projects/{project_id}/exports/``.

    Args:
        template: LaTeX template style — 'ieee', 'acm', or 'plain'.
            Defaults to 'ieee'.

    Returns:
        A dict with keys: template, section_count, tex_path, bib_path,
        and a short preview of the LaTeX output.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.export_service
        return await service.export_latex(project_id, template=template)
    except Exception as exc:
        logger.error("export_latex failed: %s", exc)
        return {"error": str(exc)}


# ------------------------------------------------------------------
# T049 – export_citation_graph
# ------------------------------------------------------------------

async def export_citation_graph(
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Export the project's paper library citation network.

    Queries Neo4j for all papers in the project and their internal
    citation relationships. Generates both a standard JSON node-link
    representation and a GraphML XML file (compatible with Gephi), saving
    them in the project exports directory.

    Returns:
        A dict with keys: node_count, edge_count, json_path, graphml_path.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id = _get_project_id(tool_context)
    if not project_id:
        return {"error": "No project_id found in session state."}

    try:
        service = ServiceRegistry.export_service
        return await service.export_citation_graph(project_id)
    except Exception as exc:
        logger.error("export_citation_graph failed: %s", exc)
        return {"error": str(exc)}
