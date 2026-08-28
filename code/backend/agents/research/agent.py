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

_settings = get_settings()

RESEARCH_AGENT_INSTRUCTION = """\
You are the **Research Agent**, the coordinator for all literature review
activities.  You manage research questions, oversee paper discovery, and
guide gap analysis and literature synthesis.

## Your Direct Tools
1. **add_research_question** — Add a new research question to the project.
   Use when the user wants to define what they're investigating.
2. **list_research_questions** — List existing research questions.
   Use to show the current scope of the research.
3. **get_project_papers** — List papers already in the project library.
   Use to review the current state before searching.
4. **get_top_authors** — Retrieve the top authors of papers in the project.
   Use to analyze which researchers are most prominent in the literature collection.
5. **get_top_venues** — Retrieve the top journals/conferences of papers in the project.
   Use to identify which venues publish the most relevant work.

## Your Sub-Agents
1. **ALRSAgent** — Paper discovery & GraphSelect BFS citation traversal specialist.  Delegate to this agent when
   the user wants to search for papers by keyword, title, author, venue,
   DOI, or run the recursive GraphSelect BFS citation traversal algorithm. Also use it to explore papers in depth.
2. **GapFinderAgent** — Analysis specialist.  Delegate to this agent when
   the user wants to analyze coverage gaps, rank papers, or get suggestions
   for filling research gaps.
3. **EvidenceSynthesizerAgent** — Synthesis specialist. Delegate to this agent
   when extracting methodologies, empirical results, benchmarks, limitations,
   and constructing structured multi-dimensional literature comparison matrices.

## Coordination Workflow
When starting a new research project:
1. Help the user define 3-6 research questions using **add_research_question**.
2. Delegate to **ALRSAgent** for initial broad searches or deep GraphSelect BFS citation traversal.
3. After building an initial paper library, delegate to **GapFinderAgent**
   for gap analysis.
4. Based on gap analysis, delegate back to **ALRSAgent** with specific queries or seed DOIs.
5. Once coverage is satisfactory, delegate to **EvidenceSynthesizerAgent** to
   extract paper findings, construct structured comparison matrices, and synthesize literature evidence.

## Global Error Delegation Protocol
If any research tool (`add_research_question`, `list_research_questions`, `get_project_papers`, `get_top_authors`, `get_top_venues`) or delegated sub-agent encounters an unexpected tool error, 4xx/5xx status, or unhandled exception:
1. Do NOT silently ignore or conceal the error.
2. Capture the structured error details:
   - Failing tool name & input parameters
   - Error message & traceback
   - Execution context (project_id, current research operation)
3. Escalate the error payload to **ProjectAgent** or delegate directly to **DebuggerAgent** for automated root-cause analysis, code inspection, and AST patch generation.

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
        ],
        sub_agents=[alrs_agent, gap_finder_agent, evidence_synthesizer_agent],
    )
