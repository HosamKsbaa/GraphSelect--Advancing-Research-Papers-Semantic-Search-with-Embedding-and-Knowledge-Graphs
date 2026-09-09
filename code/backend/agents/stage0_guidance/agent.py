"""Stage 0 Guidance & Onboarding Dialectical Pair (ParentResearchAdvisor <-> IntentAlignmentCritic)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from features.workflow.state_tools import (
    audit_intent_alignment_tool,
    complete_stage,
    formulate_intent_profile_tool,
    get_project_state,
    post_to_message_board,
    read_message_board,
)

_settings = get_settings()


def create_parent_research_advisor_agent() -> LlmAgent:
    """Create ParentResearchAdvisor builder agent for Stage 0."""
    return LlmAgent(
        name="ParentResearchAdvisor",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Analyzes research goals and synthesizes UserIntentProfile.",
        instruction="You are ParentResearchAdvisor. Formulate intent profiles from user research goals.",
        tools=[formulate_intent_profile_tool, get_project_state, post_to_message_board, read_message_board, complete_stage],
        output_key="intent_profile_result",
    )


def create_intent_alignment_critic_agent() -> LlmAgent:
    """Create IntentAlignmentCritic auditor agent for Stage 0."""
    return LlmAgent(
        name="IntentAlignmentCritic",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits user research goal feasibility and emits CritiqueVector.",
        instruction="You are IntentAlignmentCritic. Audit research intent against feasibility rubrics.",
        tools=[audit_intent_alignment_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="intent_critique_result",
    )


def create_stage0_guidance_workflow() -> SequentialAgent:
    """Create Stage 0 sequential dialectical workflow."""
    builder = create_parent_research_advisor_agent()
    critic = create_intent_alignment_critic_agent()
    return SequentialAgent(
        name="Stage0GuidanceDialecticalPair",
        sub_agents=[builder, critic],
    )


ParentResearchAdvisor = create_parent_research_advisor_agent
IntentAlignmentCritic = create_intent_alignment_critic_agent
stage0_guidance_workflow = create_stage0_guidance_workflow()

__all__ = [
    "IntentAlignmentCritic",
    "ParentResearchAdvisor",
    "create_intent_alignment_critic_agent",
    "create_parent_research_advisor_agent",
    "create_stage0_guidance_workflow",
    "stage0_guidance_workflow",
]
