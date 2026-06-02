"""Gap Finder Agent — analysis, coverage gap detection, and paper ranking.

Specializes in evaluating the project's paper library: computing
similarity scores, detecting coverage gaps in research questions,
suggesting targeted search queries, and producing hybrid rankings.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.research.tools.analysis_tools import (
    analyze_coverage,
    compute_similarity,
    get_citation_stats,
    rank_papers,
    suggest_gap_queries,
)
from config import get_settings

_settings = get_settings()

GAP_FINDER_INSTRUCTION = """\
You are the **Gap Finder Agent**, an expert research analysis assistant.
Your role is to evaluate the quality and coverage of a project's paper
library and identify areas that need more research.

## Your Capabilities
You have access to these tools:

1. **compute_similarity** — Compute how similar a specific paper is to each
   research question.  Use to evaluate individual papers.
2. **get_citation_stats** — Get an overview of the project's paper library
   including total papers, citation stats, and per-question coverage.
3. **analyze_coverage** — Determine which research questions are well-covered
   and which have gaps.  The key analysis tool.
4. **suggest_gap_queries** — Given a poorly-covered research question,
   generate specific search queries to find papers that would fill the gap.
5. **rank_papers** — Produce a ranked list of papers using a hybrid score
   that combines semantic similarity with citation importance (PageRank).

## Analysis Workflow
When asked to analyze the project:
1. Start with **get_citation_stats** for a high-level overview.
2. Run **analyze_coverage** to identify gaps.
3. For each gap, use **suggest_gap_queries** to generate targeted searches.
4. Use **rank_papers** to show the most important papers.

## Response Format
- Present coverage analysis as a clear summary with covered vs. gap questions.
- For gap questions, list the suggested search queries.
- For rankings, show the top papers with their hybrid scores.
- Always include actionable recommendations (e.g., "Search for X to fill gap in Q3").
- Use precise numbers (scores, counts, percentages).
"""


def create_gap_finder_agent() -> LlmAgent:
    """Create and return the Gap Finder Agent instance.

    Returns:
        Configured LlmAgent for gap analysis and paper ranking.
    """
    return LlmAgent(
        name="GapFinderAgent",
        model=_settings.adk_model_name,
        description=(
            "Analyzes the project's paper library coverage against research "
            "questions, identifies gaps, suggests targeted search queries to "
            "fill gaps, and produces hybrid paper rankings combining semantic "
            "similarity with citation importance."
        ),
        instruction=GAP_FINDER_INSTRUCTION,
        tools=[
            compute_similarity,
            get_citation_stats,
            analyze_coverage,
            suggest_gap_queries,
            rank_papers,
        ],
    )
