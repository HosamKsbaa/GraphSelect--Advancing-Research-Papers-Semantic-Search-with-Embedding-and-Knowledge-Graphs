"""Project Orchestrator Agent — top-level coordinator for the research pipeline.

Manages project state, delegates research tasks to the ResearchAgent,
planning to the PlannerAgent, and writing to the WriterAgent.
"""
from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent

from agents.orchestrator import create_tracing_callbacks
from agents.orchestrator.project_tools import (
    create_new_project,
    select_project,
    list_projects,
)
from agents.debugger.agent import create_debugger_agent
from agents.planner.agent import create_planner_agent
from agents.research.agent import create_research_agent
from agents.writing.agent import create_writer_agent
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
    update_stage_substate,
)

_settings = get_settings()

ORCHESTRATOR_INSTRUCTION = """\
You are the **ProjectAgent**, the top-level orchestrator for an academic
literature review project.  You guide the user through the entire research
workflow — from defining research questions to producing a polished
LaTeX document.

## Your Role
You coordinate the overall research pipeline:
1. Help users understand their project's current state.
2. Guide them through defining research questions.
3. Delegate paper discovery and analysis to the ResearchAgent.
4. Delegate outline creation to the PlannerAgent.
5. Delegate writing and exporting to the WriterAgent.
6. Delegate runtime errors, bug diagnostics, or failures to the DebuggerAgent.
7. Present progress summaries and next-step recommendations.

## Your Direct Tools
You have access to direct tools for managing project lifecycles:
1. **create_new_project** — Create and activate a new project. Use this immediately when the user asks to start a new review, investigate a new topic, or "create a project". Deduce or prompt for a short `name` and a `topic` first.
2. **select_project** — Activate an existing project. Use when the user specifies a project ID or name to work on.
3. **list_projects** — List all projects in the database. Use when the user asks what projects are available or wants to select one.

## Your Sub-Agents
- **ResearchAgent** — Handles all literature review activities including
  research question management, paper discovery (keyword/title/DOI/author/
  venue searches), paper exploration, gap analysis, and paper ranking.
  Delegate to this agent for ANY research-related task.
- **PlannerAgent** — Creates structured literature review outlines from
  ranked papers and research questions.  Delegate to this agent when
  the user wants to create an outline or plan the structure of their
  literature review.
- **WriterAgent** — Writes, reviews, and exports the literature review.
  Handles section drafting, peer review cycles, BibTeX export, and
  LaTeX document generation.  Delegate when the user wants to write
  or export their review.
- **DebuggerAgent** — Autonomous system diagnostic and bug-fixing specialist.
  Inspects backend source code, queries error traces, runs unit tests, and
  proposes AST-validated patches. Delegate to this agent whenever an unhandled
  error or tool exception occurs.

## Global Error Delegation Protocol
If you or any sub-agent encounter an unexpected tool failure, 4xx/5xx HTTP error, or runtime exception:
1. Do NOT silently ignore, mask, or drop the error.
2. Capture the structured error details:
   - Failing tool name & input parameters
   - Error message & traceback
   - Execution context (project_id, operation)
3. Delegate directly to the **DebuggerAgent** to diagnose the root cause with `fetch_error_logs` and `read_agent_code`, execute reproducing tests with `run_agent_tests`, and formulate an AST-validated fix with `validate_and_propose_patch`.

## Workflow Overview
When a user starts a new session:
1. Greet them and explain available capabilities.
2. If a project_id is set in state, report on the current project status.
3. Guide them to define research questions (via ResearchAgent).
4. Help them search for and explore papers (via ResearchAgent).
5. Periodically suggest running gap analysis (via ResearchAgent).
6. When ready, generate an outline (via PlannerAgent).
7. Draft and review sections (via WriterAgent).
8. Export final documents (via WriterAgent).

## Full Pipeline Mode
If the user says "run the full pipeline autonomously":
1. Start with research question verification.
2. Search and explore papers until adequate coverage.
3. Run gap analysis and fill gaps iteratively (up to 3 iterations).
4. Generate an outline.
5. Draft all sections with review cycles.
6. Export BibTeX and LaTeX.
7. Present a final summary with statistics.

IMPORTANT: Monitor the token budget throughout.  If you receive a budget
warning, prioritize completing the current phase and present results.

## Response Guidelines
- Be concise but informative.
- Use numbered lists and bullet points for clarity.
- Always indicate what the user can do next.
- When presenting papers, include DOI, title, year, and relevance scores.
- Track and report progress: questions defined, papers found, gaps identified.
- **IMPORTANT**: If any tool returns an "error", you MUST explicitly inform the user about the error and not hide it.
- **IMPORTANT**: When listing projects, NEVER summarize or truncate the list. You MUST output EVERY single project returned by the tool, no matter how many there are.

## State Variables
- `project_id` — The current project UUID (from session state).
- Check this before performing project-specific operations.

## Important
- You are the entry point for user interactions.
- Do NOT attempt to perform searches, analysis, planning, or writing
  directly — delegate to the appropriate sub-agent.
- If the user asks about something outside research scope, politely
  redirect them to research-related activities.
"""


def create_orchestrator_agent(
    log_service: Any | None = None,
    project_id: str | None = None,
    token_budget: int | None = None,
) -> LlmAgent:
    """Create and return the ProjectAgent (orchestrator) instance.

    Optionally attaches tracing callbacks if a LogService and project_id
    are provided.

    Args:
        log_service: Optional LogService for agent execution tracing.
        project_id: Optional project UUID for trace correlation.
        token_budget: Optional token budget override (default from config).

    Returns:
        Configured LlmAgent serving as the root orchestrator.
    """
    research_agent = create_research_agent()
    planner_agent = create_planner_agent()
    writer_agent = create_writer_agent()
    debugger_agent = create_debugger_agent()

    current_settings = get_settings()

    async def _auto_hydrate_state_callback(
        callback_context: Any,
        llm_request: Any,
    ) -> Any:
        """Ensure project_state is hydrated into session.state if project_id is present."""
        try:
            state_container = getattr(callback_context, "state", None)
            if state_container is not None and hasattr(state_container, "get"):
                project_id = state_container.get("project_id")
                if project_id and not state_container.get("project_state"):
                    from features.workflow.persistence_service import ProjectPersistenceService
                    from features.workflow.state_models import ProjectState

                    svc = ProjectPersistenceService.get_instance()
                    p_state = await svc.load_state(str(project_id), callback_context)
                    if p_state is None:
                        try:
                            from agents._service_registry import ServiceRegistry
                            from projects.service import get_project
                            mysql = ServiceRegistry.log_service._mysql
                            p = await get_project(str(project_id), mysql)
                            if p:
                                p_state = ProjectState(
                                    project_id=p.id,
                                    name=p.name,
                                    topic=p.topic or "",
                                    target_level=getattr(p, "target_level", "master") or "master",
                                    token_budget=getattr(p, "token_budget", 500000) or 500000,
                                )
                                await svc.save_state_async(p_state, callback_context)
                        except Exception as e:
                            logger.debug("Auto-hydrate project lookup failed: %s", e)

                    if p_state is not None:
                        dumped = p_state.model_dump(mode="json")
                        stages_dict = {
                            "stage_1_research": dumped.get("stage_1_research", {}),
                            "stage_2_analysis": dumped.get("stage_2_analysis", {}),
                            "stage_3_planning": dumped.get("stage_3_planning", {}),
                            "stage_4_writing": dumped.get("stage_4_writing", {}),
                            "stage_5_export": dumped.get("stage_5_export", {}),
                        }
                        state_container["project_state"] = dumped
                        state_container["stages"] = stages_dict
                        state_container["stage_1_research"] = stages_dict["stage_1_research"]
                        state_container["stage_2_analysis"] = stages_dict["stage_2_analysis"]
                        state_container["stage_3_planning"] = stages_dict["stage_3_planning"]
                        state_container["stage_4_writing"] = stages_dict["stage_4_writing"]
                        state_container["stage_5_export"] = stages_dict["stage_5_export"]
                        state_container["message_board"] = dumped.get("message_board", [])
        except Exception as exc:
            logger.debug("Auto-hydrate state callback error: %s", exc)
        return None

    def _attach_callback_recursively(agent: Any, cb: Any) -> None:
        if isinstance(agent, LlmAgent):
            existing = getattr(agent, "before_model_callback", None)
            if existing is None:
                agent.before_model_callback = cb
            elif isinstance(existing, list):
                if cb not in existing:
                    existing.append(cb)
            else:
                agent.before_model_callback = [existing, cb]
        for sub in getattr(agent, "sub_agents", []):
            _attach_callback_recursively(sub, cb)

    for agent_inst in [research_agent, planner_agent, writer_agent, debugger_agent]:
        _attach_callback_recursively(agent_inst, _auto_hydrate_state_callback)

    kwargs: dict[str, Any] = {
        "name": "ProjectAgent",
        "model": getattr(current_settings, "adk_tier1_model", current_settings.adk_model_name),
        "description": (
            "Top-level project orchestrator that coordinates the entire "
            "literature review workflow including research question definition, "
            "paper discovery, gap analysis, outline planning, section drafting, "
            "peer review, self-debugging, and LaTeX/BibTeX export."
        ),
        "instruction": ORCHESTRATOR_INSTRUCTION,
        "sub_agents": [research_agent, planner_agent, writer_agent, debugger_agent],
        "before_model_callback": _auto_hydrate_state_callback,
        "tools": [
            create_new_project,
            select_project,
            list_projects,
            get_project_state,
            post_to_message_board,
            read_message_board,
            update_stage_substate,
        ],
    }

    # Attach tracing callbacks with token budget enforcement
    if log_service is not None and project_id is not None:
        budget = token_budget or _settings.token_budget_default
        callbacks = create_tracing_callbacks(
            log_service,
            project_id,
            token_budget=budget,
            warn_threshold=_settings.token_budget_warn_threshold,
        )
        kwargs["after_model_callback"] = callbacks["after_model_callback"]
        kwargs["after_tool_callback"] = callbacks["after_tool_callback"]

    root_agent = LlmAgent(**kwargs)
    _attach_callback_recursively(root_agent, _auto_hydrate_state_callback)
    return root_agent


ProjectAgent = create_orchestrator_agent

__all__ = [
    "ORCHESTRATOR_INSTRUCTION",
    "ProjectAgent",
    "create_orchestrator_agent",
]
