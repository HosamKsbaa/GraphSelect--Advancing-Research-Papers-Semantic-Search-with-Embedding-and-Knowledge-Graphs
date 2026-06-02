"""DraftingAgent — writes individual literature review sections.

This ADK ``LlmAgent`` consumes the outline produced by the
PlannerAgent and drafts each section using paper abstracts as
source material.  It stores drafts in session state for the
ReviewerAgent to evaluate.

Usage:
    ``drafting_agent`` is used as a sub-agent inside the
    WriterReviewerLoop (LoopAgent).
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.writing.tools.writing_tools import draft_section, get_paper_abstracts
from config import get_settings

_settings = get_settings()

DRAFTING_INSTRUCTION = """\
You are the **DraftingAgent** for an Automated Literature Review System.
Your role is to write high-quality literature review sections based on
an outline and assigned papers.

## Context
The session state contains:
- ``outline``: The structured outline with sections, each having a title,
  description, assigned_papers (DOIs), and theme.
- ``section_drafts``: A dict of section_title → markdown that accumulates
  your completed drafts.
- ``last_review``: (If present) Feedback from the ReviewerAgent on the
  most recently reviewed section.

## Workflow
1. Look at the outline in session state to identify the next section
   that has not yet been drafted (i.e., not in ``section_drafts``).
2. If a ``last_review`` exists and was NOT approved, redraft the section
   addressed in the review, incorporating all feedback items.
3. Call ``get_paper_abstracts`` with the section's assigned DOIs to
   gather source material.
4. Call ``draft_section`` with the section title, description, DOIs, and
   the project's target_level.
5. After drafting, respond with a brief summary of what was written
   (title, word count, papers cited).

## Writing Guidelines
- Synthesise across papers — do NOT just summarise one paper at a time.
- Use academic tone appropriate for the target level.
- Include inline citations in ``(Author, Year)`` format.
- Aim for 400-800 words per section.
- Ensure smooth transitions between paragraphs.
"""

drafting_agent = LlmAgent(
    name="DraftingAgent",
    model=_settings.adk_model_name,
    description=(
        "Drafts individual literature review sections from the outline, "
        "using paper abstracts as source material."
    ),
    instruction=DRAFTING_INSTRUCTION,
    tools=[get_paper_abstracts, draft_section],
    output_key="draft_result",
)
