"""PlannerAgent — generates structured literature-review outlines.

This ADK ``LlmAgent`` inspects the project state, retrieves ranked
papers, and produces a sectioned outline with paper assignments. It
stores the outline in session state so downstream writing agents can
consume it.

Usage:
    ``planner_agent`` is imported by the orchestrator and registered
    as a sub-agent.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.planner.tools.outline_tools import (
    generate_outline,
    get_project_summary,
    get_ranked_papers,
)
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
    update_stage_substate,
)

_settings = get_settings()

PLANNER_INSTRUCTION = """\
You are the **PlannerAgent** for an Automated Literature Review System (ALRS).
Your job is to create a structured outline for a literature review based on
the project's research questions and collected papers.

## Workflow
1. **Start** by calling ``get_project_summary`` to understand the project's
   current state — how many papers exist, how many research questions, and
   whether an outline already exists.
2. Call ``get_ranked_papers`` to retrieve the papers ordered by a hybrid
   relevance score (semantic similarity × PageRank citation centrality).
3. Based on the summary and ranked papers, call ``generate_outline`` with an
   appropriate style:
   - ``thematic`` (default) — groups papers by research themes.
   - ``chronological`` — orders sections by time period.
   - ``methodological`` — organises by methodology.
4. Return a human-readable summary of the generated outline to the user or
   the orchestrating agent.

## Rules
- Always call ``get_project_summary`` first so you know the project state.
- If there are fewer than 3 papers, warn that the outline may be thin.
- If an outline already exists and the user has not asked for a new one,
  summarise the existing outline instead of regenerating.
- Keep your final text response concise: list the section titles, the number
  of papers assigned to each, and the narrative arc.

## Global Error Delegation Protocol
If any outline generation tool (`get_project_summary`, `get_ranked_papers`, `generate_outline`) encounters an unhandled exception or runtime failure:
1. Do NOT produce broken or hallucinated outlines.
2. Capture the structured error details:
   - Failing tool name & input parameters (style, paper count)
   - Error message & traceback
   - Execution context (project_id, outline generation step)
3. Escalate the error payload to **ProjectAgent** or delegate directly to **DebuggerAgent** for automated diagnosis, test verification, and patch proposal.
"""

def create_planner_agent() -> LlmAgent:
    """Create and return a new PlannerAgent instance."""
    settings = get_settings()
    return LlmAgent(
        name="PlannerAgent",
        model=getattr(settings, "adk_tier1_model", settings.adk_model_name),
        description=(
            "Generates structured literature review outlines from "
            "ranked papers and research questions."
        ),
        instruction=PLANNER_INSTRUCTION,
        tools=[
            get_project_summary,
            get_ranked_papers,
            generate_outline,
            get_project_state,
            post_to_message_board,
            read_message_board,
            update_stage_substate,
        ],
        output_key="planner_result",
    )


PlannerAgent = create_planner_agent
planner_agent = create_planner_agent()

__all__ = [
    "PLANNER_INSTRUCTION",
    "PlannerAgent",
    "create_planner_agent",
    "planner_agent",
]


