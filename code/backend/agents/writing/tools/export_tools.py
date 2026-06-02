"""Export tools for the WriterAgent.

Deterministic (non-LLM) tools that convert the project's paper library
and Markdown drafts into publication-ready BibTeX and LaTeX outputs.

Tools:
    - export_bibtex: Generate a .bib file from project papers
    - export_latex: Convert Markdown drafts into a LaTeX document
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import registry
from agents.writing.tex_formatter import format_to_latex, generate_bibtex
from config import get_settings

logger = logging.getLogger(__name__)


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
    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j
    settings = get_settings()

    # Fetch all project papers
    papers = await neo4j.get_project_papers(project_id, limit=500)
    if not papers:
        return {"entry_count": 0, "message": "No papers in the project to export."}

    # Generate BibTeX content
    bibtex_content: str = generate_bibtex(papers)

    # Save to disk
    export_dir = Path(settings.projects_dir) / project_id / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    bib_path = export_dir / "references.bib"
    bib_path.write_text(bibtex_content, encoding="utf-8")

    # Log
    if registry.log_service:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="WriterAgent",
            event_type="tool_call",
            details={
                "tool": "export_bibtex",
                "entry_count": len(papers),
                "path": str(bib_path),
            },
        )

    return {
        "entry_count": len(papers),
        "saved_path": str(bib_path),
        "bibtex_preview": bibtex_content[:500],
    }


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

    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j
    settings = get_settings()
    project_dir = Path(settings.projects_dir) / project_id

    # Read all draft files
    drafts_dir = project_dir / "drafts"
    if not drafts_dir.exists():
        return {"error": "No drafts directory found. Draft sections first."}

    md_files = sorted(drafts_dir.glob("*.md"))
    if not md_files:
        return {"error": "No Markdown draft files found in drafts/."}

    # Collect all Markdown content
    sections_md: list[str] = []
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        sections_md.append(content)

    combined_markdown = "\n\n".join(sections_md)

    # Collect all DOI citations from the Markdown
    # Look for DOI patterns (e.g., 10.xxxx/yyyy)
    doi_pattern = re.compile(r"10\.\d{4,9}/[^\s,)}\]]+")
    found_dois: list[str] = list(set(doi_pattern.findall(combined_markdown)))

    # Fetch paper data for BibTeX generation
    papers = await neo4j.get_project_papers(project_id, limit=500)

    # Generate BibTeX
    bibtex_content: str = generate_bibtex(papers)

    # Generate LaTeX
    latex_content: str = format_to_latex(
        markdown_content=combined_markdown,
        citations=found_dois,
        template=template,
    )

    # Save outputs
    export_dir = project_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    tex_path = export_dir / "literature_review.tex"
    tex_path.write_text(latex_content, encoding="utf-8")

    bib_path = export_dir / "references.bib"
    bib_path.write_text(bibtex_content, encoding="utf-8")

    # Log
    if registry.log_service:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="WriterAgent",
            event_type="tool_call",
            details={
                "tool": "export_latex",
                "template": template,
                "section_count": len(md_files),
                "tex_path": str(tex_path),
            },
        )

    return {
        "template": template,
        "section_count": len(md_files),
        "tex_path": str(tex_path),
        "bib_path": str(bib_path),
        "latex_preview": latex_content[:600],
    }
