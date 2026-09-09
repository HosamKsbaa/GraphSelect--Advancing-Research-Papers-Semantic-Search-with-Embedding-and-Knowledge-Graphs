"""Stage 5 Drafting & Defense Simulation Dialectical Pair (GroundedSynthesisWriter <-> AcademicRedTeamer)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from features.workflow.state_tools import (
    audit_thesis_citations_and_compiler_tool,
    complete_stage,
    draft_grounded_latex_tool,
    get_project_state,
    post_to_message_board,
    read_message_board,
)

_settings = get_settings()


def create_grounded_synthesis_writer_agent() -> LlmAgent:
    """Create GroundedSynthesisWriter builder agent for Stage 5."""
    return LlmAgent(
        name="GroundedSynthesisWriter",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Drafts IEEEtran / ACM review sections using node-bound cite-keys.",
        instruction="You are GroundedSynthesisWriter. Draft grounded LaTeX with strict AST citation keys.",
        tools=[draft_grounded_latex_tool, get_project_state, post_to_message_board, read_message_board, complete_stage],
        output_key="drafting_result",
    )


def create_academic_red_teamer_agent() -> LlmAgent:
    """Create AcademicRedTeamer auditor agent for Stage 5."""
    return LlmAgent(
        name="AcademicRedTeamer",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits 100% DOI grounding against Neo4j and validates compilation readiness.",
        instruction="You are AcademicRedTeamer. Enforce zero citation hallucination and test compiler output.",
        tools=[audit_thesis_citations_and_compiler_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="redteam_critique_result",
    )


def create_stage5_drafting_workflow() -> SequentialAgent:
    """Create Stage 5 sequential dialectical workflow."""
    builder = create_grounded_synthesis_writer_agent()
    critic = create_academic_red_teamer_agent()
    return SequentialAgent(
        name="Stage5DraftingDialecticalPair",
        sub_agents=[builder, critic],
    )


GroundedSynthesisWriter = create_grounded_synthesis_writer_agent
AcademicRedTeamer = create_academic_red_teamer_agent
stage5_drafting_workflow = create_stage5_drafting_workflow()

__all__ = [
    "AcademicRedTeamer",
    "GroundedSynthesisWriter",
    "create_academic_red_teamer_agent",
    "create_grounded_synthesis_writer_agent",
    "create_stage5_drafting_workflow",
    "stage5_drafting_workflow",
]
