"""Stage 2 Acquisition & Snowballing Dialectical Pair (SearchSnowballAgent <-> RelevanceQualityAuditor)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from features.workflow.state_tools import (
    audit_literature_quality_tool,
    complete_stage,
    get_project_state,
    post_to_message_board,
    read_message_board,
    run_alrs_snowballing_tool,
)

_settings = get_settings()


def create_search_snowball_agent() -> LlmAgent:
    """Create SearchSnowballAgent builder agent for Stage 2."""
    return LlmAgent(
        name="SearchSnowballAgent",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Performs BFS citation graph expansion and computes hybrid topological ranking.",
        instruction="You are SearchSnowballAgent. Perform citation graph snowballing traversal.",
        tools=[run_alrs_snowballing_tool, get_project_state, post_to_message_board, read_message_board, complete_stage],
        output_key="snowball_result",
    )


def create_relevance_quality_auditor_agent() -> LlmAgent:
    """Create RelevanceQualityAuditor auditor agent for Stage 2."""
    return LlmAgent(
        name="RelevanceQualityAuditor",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits retrieval precision and ensures topological bridging coverage.",
        instruction="You are RelevanceQualityAuditor. Audit candidate literature quality and bridging.",
        tools=[audit_literature_quality_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="relevance_critique_result",
    )


def create_stage2_acquisition_workflow() -> SequentialAgent:
    """Create Stage 2 sequential dialectical workflow."""
    builder = create_search_snowball_agent()
    critic = create_relevance_quality_auditor_agent()
    return SequentialAgent(
        name="Stage2AcquisitionDialecticalPair",
        sub_agents=[builder, critic],
    )


SearchSnowballAgent = create_search_snowball_agent
RelevanceQualityAuditor = create_relevance_quality_auditor_agent
stage2_acquisition_workflow = create_stage2_acquisition_workflow()

__all__ = [
    "RelevanceQualityAuditor",
    "SearchSnowballAgent",
    "create_relevance_quality_auditor_agent",
    "create_search_snowball_agent",
    "create_stage2_acquisition_workflow",
    "stage2_acquisition_workflow",
]
