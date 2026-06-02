"""Review tool for the ReviewerAgent.

Provides a tool that evaluates a drafted section for accuracy,
completeness, citation coverage, and coherence using the LLM.

Tools:
    - review_section: LLM-driven section review with structured feedback
"""
from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import registry
from core.llm.models import CompletionRequest

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# T046 – review_section
# ------------------------------------------------------------------

async def review_section(
    section_title: str,
    draft_markdown: str,
    assigned_dois: list[str],
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Review a drafted section for accuracy, completeness, and coherence.

    Evaluates the section against academic standards, checking citation
    coverage, logical flow, synthesis quality, and factual consistency
    with the source papers.

    Args:
        section_title: Title of the section being reviewed.
        draft_markdown: The full Markdown text of the draft.
        assigned_dois: List of DOIs that should be cited in this section.

    Returns:
        A dict with keys:
        - approved (bool): True if the section meets quality standards.
        - feedback (list[str]): Specific improvement suggestions.
        - missing_citations (list[str]): DOIs assigned but not cited.
        - scores (dict): Sub-scores for coverage, coherence, synthesis.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id: str = tool_context.state.get("project_id", "")
    llm = registry.llm

    # Pre-check: which assigned DOIs appear in the draft?
    missing_citations: list[str] = [
        doi for doi in assigned_dois if doi not in draft_markdown
    ]

    prompt = f"""You are an expert academic reviewer evaluating a literature review section.

## Section Title
{section_title}

## Draft
{draft_markdown}

## Assigned Papers (DOIs)
{json.dumps(assigned_dois)}

## Missing Citations (DOIs assigned but NOT appearing in draft)
{json.dumps(missing_citations)}

## Evaluation Criteria
Rate each criterion on a scale of 1-5 and provide specific feedback:
1. **Citation Coverage** — Are all assigned papers cited and discussed?
2. **Coherence** — Does the section flow logically? Are transitions smooth?
3. **Synthesis Quality** — Does the section synthesise across papers
   (comparing, contrasting, identifying patterns) rather than summarising
   each paper individually?
4. **Academic Tone** — Is the writing appropriate for an academic
   literature review?
5. **Completeness** — Is the section thorough enough (typically 400-800 words)?

## Response Format
Respond in valid JSON:
{{
  "approved": true/false,
  "scores": {{
    "citation_coverage": 1-5,
    "coherence": 1-5,
    "synthesis": 1-5,
    "academic_tone": 1-5,
    "completeness": 1-5
  }},
  "feedback": ["specific suggestion 1", "specific suggestion 2", ...],
  "missing_citations": ["doi1", ...]
}}

Set "approved" to true ONLY if ALL scores are >= 4 AND there are no
missing citations.
"""

    request = CompletionRequest(
        prompt=prompt,
        system_instruction=(
            "You are a strict academic reviewer. "
            "Respond ONLY with valid JSON matching the requested schema."
        ),
        temperature=0.3,
        max_tokens=2048,
        response_format="application/json",
    )

    response = await llm.complete(request)
    raw_text = response.text.strip()

    # Strip markdown code fences
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        review_data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError:
        # If parsing fails, return a cautious non-approval
        review_data = {
            "approved": False,
            "scores": {},
            "feedback": [
                "Review parsing failed. Please revise the section and try again.",
                f"Raw reviewer output: {raw_text[:500]}",
            ],
            "missing_citations": missing_citations,
        }

    # Ensure missing_citations from our pre-check are included
    review_missing = review_data.get("missing_citations", [])
    all_missing = list(set(missing_citations + review_missing))
    review_data["missing_citations"] = all_missing

    # Store review result in session state
    tool_context.state["last_review"] = review_data

    # Log trace
    if registry.log_service and project_id:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="ReviewerAgent",
            event_type="tool_call",
            token_count=response.usage.total_tokens,
            details={
                "tool": "review_section",
                "section": section_title,
                "approved": review_data.get("approved", False),
                "scores": review_data.get("scores", {}),
            },
        )

    return review_data
