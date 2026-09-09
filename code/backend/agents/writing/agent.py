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

from typing import Any

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent

from agents.writing.drafting_agent import create_drafting_agent, drafting_agent
from agents.writing.reviewer_agent import create_reviewer_agent, reviewer_agent
from agents.writing.tools.export_tools import export_bibtex, export_latex, export_citation_graph
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
    update_stage_substate,
)

_settings = get_settings()


def _safe_agent_eq(self: BaseAgent, other: Any) -> bool:
    """Cycle-safe equality for ADK agent instances."""
    if self is other:
        return True
    if not isinstance(other, BaseAgent):
        return False
    return self.name == other.name and type(self) is type(other)


setattr(BaseAgent, "__eq__", _safe_agent_eq)


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

## Global Error Delegation Protocol
If drafting, review loop iteration, or document export (`export_bibtex`, `export_latex`, `export_citation_graph`) encounters an unhandled exception or runtime error:
1. Do NOT silently fail or produce corrupted export artifacts.
2. Capture the structured error details:
   - Failing tool name & input parameters (section title, export format, paths)
   - Error message & traceback
   - Execution context (project_id, export or loop operation)
3. Escalate the error payload to **ProjectAgent** or delegate directly to **DebuggerAgent** for automated diagnostic inspection and AST-validated resolution.

## Notes
- If the outline is not available in session state, ask the user to
  run the PlannerAgent first.
- For each section, provide the WriterReviewerLoop with the section
  title, description, and assigned papers via the conversation.
- Use the ``export_bibtex`` and ``export_latex`` tools directly — they
  are deterministic and do not require LLM calls.
"""


def create_writer_agent() -> LlmAgent:
    """Create and return a new WriterAgent instance with fresh sub-agents."""
    drafting = create_drafting_agent()
    reviewer = create_reviewer_agent()
    loop = LoopAgent(
        name="WriterReviewerLoop",
        sub_agents=[drafting, reviewer],
        max_iterations=3,
    )
    return LlmAgent(
        name="WriterAgent",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description=(
            "Orchestrates the full writing pipeline: iterative draft-review "
            "cycles for each section, then BibTeX and LaTeX export."
        ),
        instruction=WRITER_INSTRUCTION,
        sub_agents=[loop],
        tools=[
            export_bibtex,
            export_latex,
            export_citation_graph,
            get_project_state,
            post_to_message_board,
            read_message_board,
            update_stage_substate,
        ],
        output_key="writer_result",
    )


WriterAgent = create_writer_agent
writer_agent = create_writer_agent()
writer_reviewer_loop = writer_agent.sub_agents[0]

__all__ = [
    "WRITER_INSTRUCTION",
    "WriterAgent",
    "create_writer_agent",
    "writer_agent",
    "writer_reviewer_loop",
]


