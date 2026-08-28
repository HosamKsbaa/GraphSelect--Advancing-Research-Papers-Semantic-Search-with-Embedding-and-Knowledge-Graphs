"""ReviewerAgent — critically evaluates drafted literature review sections.

This ADK ``LlmAgent`` evaluates drafts produced by the DraftingAgent,
scoring them on citation coverage, coherence, synthesis quality,
academic tone, and completeness.  It stores its review verdict in
session state so the LoopAgent can coordinate re-drafting if needed.

Usage:
    ``reviewer_agent`` is used as a sub-agent inside the
    WriterReviewerLoop (LoopAgent), running after the DraftingAgent.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from agents.writing.tools.review_tools import review_section
from config import get_settings

_settings = get_settings()


# ------------------------------------------------------------------
# Exit-loop tool: signals the LoopAgent to stop iterating
# ------------------------------------------------------------------

def exit_loop(tool_context: ToolContext) -> dict[str, str]:
    """Signal the LoopAgent to stop iterating.

    Call this function ONLY when the review indicates the draft is
    approved (all scores >= 4 and no missing citations).  This will
    escalate control back to the parent WriterAgent.

    Returns:
        An empty dict (the escalation is a side-effect).
    """
    tool_context.actions.escalate = True
    tool_context.actions.skip_summarization = True
    return {"status": "loop_exited"}


REVIEWER_INSTRUCTION = """\
You are the **ReviewerAgent** for an Automated Literature Review System.
Your role is to critically evaluate drafted literature review sections
and decide whether they meet publication-quality standards.

## Context
The session state contains:
- ``section_drafts``: A dict of section_title → markdown containing
  the latest drafts from the DraftingAgent.
- ``draft_result``: The DraftingAgent's most recent output summary.
- ``outline``: The outline with section assignments.

## Workflow
1. Identify the section that was most recently drafted (from
   ``draft_result`` or by inspecting ``section_drafts``).
2. Retrieve the full Markdown draft from ``section_drafts``.
3. Determine the assigned DOIs from the ``outline``.
4. Call ``review_section`` with the section title, draft markdown,
   and assigned DOIs.
5. Analyse the returned review scores and feedback.
6. **If approved** (all scores >= 4, no missing citations):
   - Call ``exit_loop`` to stop the write-review cycle.
7. **If NOT approved**:
   - Respond with a concise summary of what needs to be improved,
     referencing the specific feedback items.  The DraftingAgent will
     see this in the next iteration via ``last_review`` state.

## Rules
- Be strict but fair.  Do not approve sections that merely summarise
  papers without synthesis.
- Always check for missing citations — all assigned DOIs should appear.
- If scores are borderline (3-4), lean towards requesting improvement
  unless the overall quality is strong.

## Global Error Delegation Protocol
If section review (`review_section`) or loop exit (`exit_loop`) encounters an unhandled exception or runtime failure:
1. Do NOT approve or drop unreviewed sections silently.
2. Capture the structured error details:
   - Failing tool name & input parameters (section title, draft snippet, assigned DOIs)
   - Error message & traceback
   - Execution context (project_id, review iteration)
3. Escalate the error payload to parent **WriterAgent** / **DebuggerAgent** for automated diagnostics and corrective action.
"""

def create_reviewer_agent() -> LlmAgent:
    """Create and return a new ReviewerAgent instance."""
    return LlmAgent(
        name="ReviewerAgent",
        model=getattr(_settings, "adk_tier1_model", _settings.adk_model_name),
        description=(
            "Reviews drafted sections for citation coverage, coherence, "
            "synthesis quality, and academic standards."
        ),
        instruction=REVIEWER_INSTRUCTION,
        tools=[review_section, exit_loop],
        output_key="review_result",
    )


reviewer_agent = create_reviewer_agent()

