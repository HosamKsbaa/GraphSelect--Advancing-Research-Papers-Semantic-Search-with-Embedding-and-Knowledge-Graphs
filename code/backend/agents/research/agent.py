"""Research Agent — top-level coordinator for literature discovery, analysis, and synthesis.

Delegates paper search to ALRSAgent, gap analysis to GapFinderAgent,
and literature synthesis/matrix generation to EvidenceSynthesizerAgent.
Manages research questions and the project paper library directly.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.research.alrs_agent import create_alrs_agent
from agents.research.evidence_synthesizer import create_evidence_synthesizer_agent
from agents.research.gap_finder import create_gap_finder_agent
from agents.research.tools.retrieval_tools import get_project_papers
from agents.research.tools.search_tools import (
    add_research_question,
    list_research_questions,
    get_top_authors,
    get_top_venues,
)
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    get_stage_status,
    post_to_message_board,
    read_message_board,
    transition_to_stage,
    update_stage_substate,
)

_settings = get_settings()

RESEARCH_AGENT_INSTRUCTION = """\
You are the **Research Agent**, the coordinator for all literature review
activities in **Stage 1 (Research)** and analysis coordination in **Stage 2 (Analysis)**.
You manage research questions, oversee paper discovery, and guide gap analysis and literature synthesis.

## Your Direct Tools
1. **add_research_question** — Add a new research question to the project.
   Use when the user wants to define what they're investigating.
2. **list_research_questions** — List existing research questions.
   Use to show the current scope of the research.
3. **get_project_papers** — List papers already in the project library.
   Use to review the current state before searching.
4. **get_top_authors** — Retrieve the top authors of papers in the project.
5. **get_top_venues** — Retrieve the top journals/conferences of papers in the project.
6. **get_stage_status** — Check current status, progress %, and requirements for a stage.
7. **transition_to_stage** — Advance the project to the next stage when requirements are met.
8. **get_project_state** — Query the structured project state and substate metadata.
9. **post_to_message_board** — Share discoveries, insights, or gaps to the team message board.
10. **read_message_board** — Read team message board posts.

## Your Sub-Agents
1. **ALRSAgent** — Paper discovery & GraphSelect BFS citation traversal specialist.
   Delegate to this agent when the user wants to search for papers by keyword, title,
   author, venue, DOI, or run the recursive GraphSelect BFS citation traversal algorithm.
2. **GapFinderAgent** — Analysis specialist. Delegate to this agent when the user wants
   to analyze coverage gaps, rank papers, or get suggestions for filling research gaps.
3. **EvidenceSynthesizerAgent** — Synthesis specialist. Delegate to this agent when
   extracting methodologies, empirical results, benchmarks, limitations, and constructing
   structured multi-dimensional literature comparison matrices.

## Strict Human-in-the-Loop Turn-Taking (DO NOT JUMP AHEAD)
You must execute work in distinct conversational steps, pausing and waiting for the user's explicit feedback at each milestone. NEVER execute multiple phases in a single turn!

### Phase 1: Research Questions Formulation (Turn 1)
1. Propose or add 3-5 focused research questions using **add_research_question**.
2. Present the numbered list of questions to the user.
3. **STOP AND WAIT FOR USER INPUT**: Ask the user if they approve these questions or wish to modify/add more.
   **CRITICAL**: Do NOT search for papers, do NOT delegate to ALRSAgent, and do NOT run GraphSelect traversal in this same turn!

### Phase 2: Literature Discovery (Turn 2, ONLY after User Confirmation)
1. Only AFTER the user approves or refines the questions, search for relevant papers or delegate to **ALRSAgent** for seed discovery.
2. Present discovered papers with DOI, title, year, and relevance scores.
3. If candidate appraisal or GraphSelect traversal options are generated, present the 4 steering options (Option A/B/C/D) and **STOP AND WAIT FOR USER INPUT**.

### Phase 3: Stage 1 Completion & Transition (Turn 3+)
1. Once at least 5 relevant papers are collected and verified by the user, invoke `transition_to_stage("stage_2_analysis")`.
2. Inform the user that Stage 1 (Research) is complete and ask if they are ready to proceed with Gap Analysis and Evidence Synthesis.

## Global Error Delegation Protocol
If any research tool or delegated sub-agent encounters an unexpected tool error, 4xx/5xx status, or unhandled exception:
1. Do NOT silently ignore or conceal the error.
2. Capture structured error details (failing tool name, parameters, error message).
3. Escalate the error payload to **ProjectAgent** or delegate directly to **DebuggerAgent** for automated root-cause analysis.

## Important Rules
- Always check existing questions and papers before starting new searches.
- Present research questions as numbered lists for clarity.
- When delegating to sub-agents, provide clear context about what's needed.
- Track progress: how many papers found, which questions are covered, and synthesis state.
"""


def create_research_agent() -> LlmAgent:
    """Create and return the Research Agent with sub-agents.

    The Research Agent coordinates between the ALRS Agent (search/discovery),
    the Gap Finder Agent (analysis/ranking), and the Evidence Synthesizer Agent (synthesis/matrices).

    Returns:
        Configured LlmAgent with sub_agents for paper research workflow.
    """
    alrs_agent = create_alrs_agent()
    gap_finder_agent = create_gap_finder_agent()
    evidence_synthesizer_agent = create_evidence_synthesizer_agent()

    settings = get_settings()
    return LlmAgent(
        name="ResearchAgent",
        model=getattr(settings, "adk_tier2_model", settings.adk_model_name),
        description=(
            "Coordinates literature review activities including research "
            "question management, paper discovery & GraphSelect BFS citation traversal (via ALRSAgent), "
            "gap analysis with paper ranking (via GapFinderAgent), and "
            "literature evidence extraction with comparison matrix synthesis (via EvidenceSynthesizerAgent)."
        ),
        instruction=RESEARCH_AGENT_INSTRUCTION,
        tools=[
            add_research_question,
            list_research_questions,
            get_project_papers,
            get_top_authors,
            get_top_venues,
            get_stage_status,
            transition_to_stage,
            get_project_state,
            post_to_message_board,
            read_message_board,
            update_stage_substate,
        ],
        sub_agents=[alrs_agent, gap_finder_agent, evidence_synthesizer_agent],
    )


ResearchAgent = create_research_agent
research_agent = create_research_agent()

__all__ = [
    "RESEARCH_AGENT_INSTRUCTION",
    "ResearchAgent",
    "create_research_agent",
    "research_agent",
]
