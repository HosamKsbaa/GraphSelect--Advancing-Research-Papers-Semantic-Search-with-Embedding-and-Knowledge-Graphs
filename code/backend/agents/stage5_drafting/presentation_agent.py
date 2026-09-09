"""Google ADK PresentationAgent builder agent for Stage 5 Drafting & Defense.

Conforms to Constitution Rules A28, A33, A36, C9.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.tools.presentation_tools import generate_presentation_deck_tool
from config import get_settings
from features.workflow.state_tools import (
    get_project_state,
    post_to_message_board,
    read_message_board,
)

_settings = get_settings()


def create_presentation_agent() -> LlmAgent:
    """Create Google ADK PresentationAgent builder for synthesizing slide decks."""
    return LlmAgent(
        name="PresentationAgent",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Synthesizes audience-focused, graph-grounded interactive presentation decks.",
        instruction=(
            "You are PresentationAgent, an expert academic presenter for thesis defense and seminars. "
            "Extract verified epistemic facts from Neo4j SSOT, structure audience-tailored slide sequences, "
            "and render standalone offline HTML presentation decks with zero citation hallucination."
        ),
        tools=[
            generate_presentation_deck_tool,
            get_project_state,
            post_to_message_board,
            read_message_board,
        ],
        output_key="presentation_deck_result",
    )


PresentationAgent = create_presentation_agent

__all__ = [
    "PresentationAgent",
    "create_presentation_agent",
]
