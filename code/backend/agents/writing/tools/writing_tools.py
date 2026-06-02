"""Writing tools for the DraftingAgent.

Provides tools for retrieving paper abstracts and drafting individual
sections of the literature review using the LLM.

Tools:
    - get_paper_abstracts: batch-fetch abstracts by DOI list
    - draft_section: LLM-driven section drafting with citations
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import registry
from config import get_settings
from core.llm.models import CompletionRequest

logger = logging.getLogger(__name__)


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
    if not dois:
        return {"papers": [], "message": "No DOIs provided."}

    neo4j = registry.neo4j
    results: list[dict[str, Any]] = []

    for doi in dois:
        paper = await neo4j.get_paper_by_doi(doi)
        if paper:
            results.append({
                "doi": paper.get("doi", doi),
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract") or "Abstract not available.",
                "year": paper.get("year"),
                "source": paper.get("source"),
            })
        else:
            results.append({
                "doi": doi,
                "title": "Unknown",
                "abstract": "Paper not found in the knowledge graph.",
                "year": None,
                "source": None,
            })

    project_id: str = tool_context.state.get("project_id", "")
    if registry.log_service and project_id:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="DraftingAgent",
            event_type="tool_call",
            details={
                "tool": "get_paper_abstracts",
                "requested": len(dois),
                "found": sum(1 for r in results if r["title"] != "Unknown"),
            },
        )

    return {"papers": results}


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

    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j
    llm = registry.llm
    settings = get_settings()

    # Fetch paper details for the prompt
    paper_blocks: list[str] = []
    for doi in paper_dois:
        paper = await neo4j.get_paper_by_doi(doi)
        if paper:
            abstract_text = (paper.get("abstract") or "No abstract available.")[:600]
            paper_blocks.append(
                f"[{doi}]\n"
                f"  Title: {paper.get('title', 'Unknown')}\n"
                f"  Year: {paper.get('year', 'N/A')}\n"
                f"  Abstract: {abstract_text}"
            )
        else:
            paper_blocks.append(f"[{doi}]\n  Title: Unknown\n  Year: N/A")

    papers_text = "\n\n".join(paper_blocks) if paper_blocks else "No source papers available."

    level_guidance = (
        "Write at a level suitable for a master's thesis. "
        "Use clear, accessible academic language."
        if target_level == "master"
        else "Write at a level suitable for a doctoral dissertation. "
        "Use sophisticated academic language and deeper critical analysis."
    )

    prompt = f"""You are an expert academic writer preparing a literature review section.

## Section
Title: {section_title}
Description: {section_description}

## Source Papers
{papers_text}

## Requirements
1. {level_guidance}
2. Write 400-800 words in Markdown format.
3. Start with a brief introduction to the section's theme.
4. Synthesise — do NOT just summarise papers one-by-one.  Compare,
   contrast, and identify patterns across sources.
5. Use inline citations in the format ``(AuthorLastName, Year)`` where
   Author is derived from the paper title/DOI context.  If the author
   name is unknown, use ``(DOI: <short-doi>)`` instead.
6. End with a brief transition sentence leading to the next section.
7. Do NOT include section numbers or the word "Section" in the heading.
8. Output ONLY the Markdown text.  Do not add meta-commentary.
"""

    request = CompletionRequest(
        prompt=prompt,
        system_instruction="You are an academic writing assistant. Produce only the requested Markdown.",
        temperature=0.5,
        max_tokens=4096,
    )

    response = await llm.complete(request)
    markdown: str = response.text.strip()

    # Count words
    word_count: int = len(markdown.split())

    # Determine which DOIs were actually cited
    cited_dois: list[str] = [doi for doi in paper_dois if doi in markdown]

    # Save to disk
    slug = re.sub(r"[^a-z0-9]+", "_", section_title.lower()).strip("_")[:60]
    draft_dir = Path(settings.projects_dir) / project_id / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{slug}.md"
    draft_path.write_text(markdown, encoding="utf-8")

    # Store in session state for the reviewer
    drafts_state: dict[str, str] = tool_context.state.get("section_drafts", {})
    drafts_state[section_title] = markdown
    tool_context.state["section_drafts"] = drafts_state

    # Log trace
    if registry.log_service:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="DraftingAgent",
            event_type="tool_call",
            token_count=response.usage.total_tokens,
            details={
                "tool": "draft_section",
                "section": section_title,
                "word_count": word_count,
                "cited_dois": len(cited_dois),
            },
        )

    return {
        "section_title": section_title,
        "markdown": markdown,
        "word_count": word_count,
        "cited_dois": cited_dois,
        "saved_path": str(draft_path),
    }
