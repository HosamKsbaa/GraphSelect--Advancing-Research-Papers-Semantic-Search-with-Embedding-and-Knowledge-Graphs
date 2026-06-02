"""Root agent definition and ADK application entry point.

This module creates the root agent for the ALRS v2 agentic research
workflow.  The orchestrator (ProjectAgent) serves as the root agent,
coordinating all sub-agents in the hierarchy:

    ProjectAgent (orchestrator)
    ├── ResearchAgent (coordinator)
    │   ├── ALRSAgent (paper discovery)
    │   └── GapFinderAgent (analysis & ranking)
    ├── PlannerAgent (outline generation)
    └── WriterAgent (writing & export)
        └── WriterReviewerLoop (LoopAgent)
            ├── DraftingAgent (section drafting)
            └── ReviewerAgent (peer review)

The ``create_root_agent()`` function builds the full hierarchy and
returns the root LlmAgent.  The module-level ``root_agent`` variable
is the ADK entry point.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.orchestrator.agent import create_orchestrator_agent


def create_root_agent() -> LlmAgent:
    """Build and return the full agent hierarchy.

    Creates the orchestrator agent which internally creates all
    sub-agents: ResearchAgent (with ALRSAgent + GapFinderAgent),
    PlannerAgent, and WriterAgent (with DraftingAgent + ReviewerAgent).

    Returns:
        The root LlmAgent (ProjectAgent) with full sub-agent tree.
    """
    orchestrator = create_orchestrator_agent()
    return orchestrator


# ADK entry point — this is what ADK looks for when loading the agent
root_agent = create_root_agent()
