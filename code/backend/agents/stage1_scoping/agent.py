"""Stage 1 Scoping & Gap Triage Dialectical Pair (SocraticScopingAdvisor <-> ScopeBoundariesCritic)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from features.workflow.state_tools import (
    audit_scope_boundaries_tool,
    complete_stage,
    get_project_state,
    post_to_message_board,
    read_message_board,
    synthesize_finer_rq_tool,
)

_settings = get_settings()


def create_socratic_scoping_advisor_agent() -> LlmAgent:
    """Create SocraticScopingAdvisor builder agent for Stage 1."""
    return LlmAgent(
        name="SocraticScopingAdvisor",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Synthesizes up to 6 falsifiable FINER research questions with explicit margins.",
        instruction="You are SocraticScopingAdvisor. Synthesize FINER research questions.",
        tools=[synthesize_finer_rq_tool, get_project_state, post_to_message_board, read_message_board, complete_stage],
        output_key="scoping_advisor_result",
    )


def create_scope_boundaries_critic_agent() -> LlmAgent:
    """Create ScopeBoundariesCritic (Reviewer #2) auditor agent for Stage 1."""
    return LlmAgent(
        name="ScopeBoundariesCritic",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits FINER criteria, non-inferiority margins, and literature recency collision.",
        instruction="You are ScopeBoundariesCritic. Audit research question boundaries and compliance.",
        tools=[audit_scope_boundaries_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="scoping_critique_result",
    )


def create_stage1_scoping_workflow() -> SequentialAgent:
    """Create Stage 1 sequential dialectical workflow."""
    builder = create_socratic_scoping_advisor_agent()
    critic = create_scope_boundaries_critic_agent()
    return SequentialAgent(
        name="Stage1ScopingDialecticalPair",
        sub_agents=[builder, critic],
    )


SocraticScopingAdvisor = create_socratic_scoping_advisor_agent
ScopeBoundariesCritic = create_scope_boundaries_critic_agent
stage1_scoping_workflow = create_stage1_scoping_workflow()

__all__ = [
    "ScopeBoundariesCritic",
    "SocraticScopingAdvisor",
    "create_scope_boundaries_critic_agent",
    "create_socratic_scoping_advisor_agent",
    "create_stage1_scoping_workflow",
    "stage1_scoping_workflow",
]
