"""Stage 5 Drafting & Defense Simulation agent package."""
from agents.stage5_drafting.agent import (
    AcademicRedTeamer,
    GroundedSynthesisWriter,
    create_academic_red_teamer_agent,
    create_grounded_synthesis_writer_agent,
    create_stage5_drafting_workflow,
    stage5_drafting_workflow,
)
from agents.stage5_drafting.presentation_agent import (
    PresentationAgent,
    create_presentation_agent,
)
from agents.stage5_drafting.critic_agent import (
    SlideGroundingCritic,
    create_slide_grounding_critic,
)

__all__ = [
    "AcademicRedTeamer",
    "GroundedSynthesisWriter",
    "PresentationAgent",
    "SlideGroundingCritic",
    "create_academic_red_teamer_agent",
    "create_grounded_synthesis_writer_agent",
    "create_presentation_agent",
    "create_slide_grounding_critic",
    "create_stage5_drafting_workflow",
    "stage5_drafting_workflow",
]

