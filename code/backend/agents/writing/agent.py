"""WriterAgent — top-level writing pipeline with draft-review loop.

Orchestrates the writing workflow:
1. A ``LoopAgent`` (WriterReviewerLoop) iterates between the
   DraftingAgent and ReviewerAgent up to 3 times per section.
2. The WriterAgent itself holds the export tools (BibTeX, LaTeX)
   which are called after all sections are drafted and approved.

Usage:
    ``writer_agent`` is imported by the orchestrator and registered
    as a sub-agent.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent

from agents.writing.drafting_agent import drafting_agent
from agents.writing.reviewer_agent import reviewer_agent
from agents.writing.tools.export_tools import export_bibtex, export_latex, export_citation_graph
from config import get_settings

_settings = get_settings()

# ------------------------------------------------------------------
# Writer-Reviewer Loop (LoopAgent)
# ------------------------------------------------------------------

writer_reviewer_loop = LoopAgent(
    name="WriterReviewerLoop",
    sub_agents=[drafting_agent, reviewer_agent],
    max_iterations=3,
)

# ------------------------------------------------------------------
# WriterAgent (LlmAgent wrapping the loop + export tools)
# ------------------------------------------------------------------

WRITER_INSTRUCTION = """\
You are the **WriterAgent** for an Automated Literature Review System.
You coordinate the full writing pipeline: drafting sections, reviewing
them, and exporting the final output.

## Context
The session state should contain:
- ``outline``: Structured outline from the PlannerAgent with sections,
  each listing title, description, assigned_papers, and theme.
- ``project_id``: The current project identifier.

## Workflow
1. For each section in the outline, delegate to the
   ``WriterReviewerLoop`` sub-agent.  It will draft and review the
   section (up to 3 iterations) until approved or max iterations.
2. After ALL sections have been drafted and reviewed, call the
   ``export_bibtex`` tool to generate a BibTeX bibliography.
3. Call the ``export_latex`` tool to produce a LaTeX document from
   the approved Markdown drafts.
4. Call the ``export_citation_graph`` tool to generate standard JSON
   and GraphML citation graph exports.
5. Respond with a summary: number of sections written, total word
   count, export file paths, and any sections that were not fully
   approved.

## Notes
- If the outline is not available in session state, ask the user to
  run the PlannerAgent first.
- For each section, provide the WriterReviewerLoop with the section
  title, description, and assigned papers via the conversation.
- Use the ``export_bibtex`` and ``export_latex`` tools directly — they
  are deterministic and do not require LLM calls.
"""

writer_agent = LlmAgent(
    name="WriterAgent",
    model=_settings.adk_model_name,
    description=(
        "Orchestrates the full writing pipeline: iterative draft-review "
        "cycles for each section, then BibTeX and LaTeX export."
    ),
    instruction=WRITER_INSTRUCTION,
    sub_agents=[writer_reviewer_loop],
    tools=[export_bibtex, export_latex, export_citation_graph],
    output_key="writer_result",
)


def create_writer_agent() -> LlmAgent:
    """Create and return the WriterAgent instance."""
    return writer_agent

