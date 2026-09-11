"""Stage 4 Synthesis & Blueprinting Dialectical Pair (MethodologyArchitect <-> NoveltyRigorChallenger)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from agents.tools.autonomous_enhancement_tools import generate_section_synthesis_matrix_tool
from features.workflow.state_tools import (
    audit_methodology_rigor_tool,
    complete_stage,
    get_project_state,
    post_to_message_board,
    read_message_board,
    synthesize_comparison_matrix_tool,
)

_settings = get_settings()


def create_methodology_architect_agent() -> LlmAgent:
    """Create MethodologyArchitect builder agent for Stage 4."""
    return LlmAgent(
        name="MethodologyArchitect",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Constructs structured methodology comparative matrices, section synthesis matrices, and surfaces contradictions.",
        instruction="You are MethodologyArchitect. Synthesize structured comparison matrices and section synthesis matrices.",
        tools=[
            synthesize_comparison_matrix_tool,
            generate_section_synthesis_matrix_tool,
            get_project_state,
            post_to_message_board,
            read_message_board,
            complete_stage,
        ],
        output_key="synthesis_result",
    )


def create_novelty_rigor_challenger_agent() -> LlmAgent:
    """Create NoveltyRigorChallenger auditor agent for Stage 4."""
    return LlmAgent(
        name="NoveltyRigorChallenger",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits comparative matrix completeness, rigor, and contradiction surfacing.",
        instruction="You are NoveltyRigorChallenger. Audit comparison matrix and evaluate methodological rigor.",
        tools=[audit_methodology_rigor_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="novelty_critique_result",
    )


def create_stage4_synthesis_workflow() -> SequentialAgent:
    """Create Stage 4 sequential dialectical workflow."""
    builder = create_methodology_architect_agent()
    critic = create_novelty_rigor_challenger_agent()
    return SequentialAgent(
        name="Stage4SynthesisDialecticalPair",
        sub_agents=[builder, critic],
    )


MethodologyArchitect = create_methodology_architect_agent
NoveltyRigorChallenger = create_novelty_rigor_challenger_agent
stage4_synthesis_workflow = create_stage4_synthesis_workflow()

__all__ = [
    "MethodologyArchitect",
    "NoveltyRigorChallenger",
    "create_methodology_architect_agent",
    "create_novelty_rigor_challenger_agent",
    "create_stage4_synthesis_workflow",
    "stage4_synthesis_workflow",
]
