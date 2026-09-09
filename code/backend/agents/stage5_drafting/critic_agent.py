"""Google ADK SlideGroundingCritic adversarial auditor for Stage 5 Drafting & Defense.

Conforms to Constitution Rules A28, A33, A36, A37, C9.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.tools.presentation_tools import audit_slide_grounding_tool
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
)

_settings = get_settings()


def create_slide_grounding_critic() -> LlmAgent:
    """Create Google ADK SlideGroundingCritic adversarial auditor for slide grounding."""
    return LlmAgent(
        name="SlideGroundingCritic",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits slide decks against Neo4j SSOT enforcing zero citation hallucination (CHR == 0.0%).",
        instruction=(
            "You are SlideGroundingCritic, an adversarial fact auditor for academic slide decks. "
            "Rigorously verify that 100% of cited DOIs exist in the campaign Neo4j graph. "
            "Reject any slide candidate containing ungrounded claims, metric drift, or missing speaker notes."
        ),
        tools=[
            audit_slide_grounding_tool,
            get_project_state,
            post_to_message_board,
            read_message_board,
        ],
        output_key="slide_critique_result",
    )


SlideGroundingCritic = create_slide_grounding_critic

__all__ = [
    "SlideGroundingCritic",
    "create_slide_grounding_critic",
]
