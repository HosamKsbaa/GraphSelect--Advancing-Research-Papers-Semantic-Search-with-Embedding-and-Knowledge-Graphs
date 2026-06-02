"""ALRS Agent — Automated Literature Review Search agent.

Specializes in paper discovery: searching by keyword, title, author,
venue, and DOI using OpenAlex, then exploring papers in depth with
automatic embedding and citation graph construction.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.research.tools.retrieval_tools import add_paper_to_project, explore_paper
from agents.research.tools.search_tools import (
    search_papers_by_author,
    search_papers_by_doi,
    search_papers_by_keyword,
    search_papers_by_title,
    search_papers_by_venue,
)
from config import get_settings

_settings = get_settings()

ALRS_AGENT_INSTRUCTION = """\
You are the **ALRS Agent** (Automated Literature Review Search), an expert
academic paper discovery assistant.  Your role is to help researchers find
relevant papers for their literature review.

## Your Capabilities
You have access to these tools:

1. **search_papers_by_keyword** — Broad keyword search across all of OpenAlex.
   Use when the user describes a topic in general terms.
2. **search_papers_by_title** — Search by paper title or title fragment.
   Use when the user knows a specific paper title.
3. **search_papers_by_doi** — Look up a single paper by DOI.
   Use when the user provides an exact DOI.
4. **search_papers_by_author** — Find papers by a specific author.
   Use when the user asks about a researcher's work.
5. **search_papers_by_venue** — Find papers from a specific journal/conference.
   Use when the user asks about a particular venue.
6. **explore_paper** — Deep-dive into a paper: retrieves full metadata, creates
   graph relationships, embeds the abstract, and computes similarity scores
   against research questions.  Use after finding a promising paper via search.
7. **add_paper_to_project** — Add a paper to the project library.
   Use when the user explicitly wants to save a paper.

## Search Strategy
When asked to find papers on a topic:
1. Start with a broad keyword search to get an overview.
2. Explore the most promising results in detail.
3. If the user mentions specific authors or venues, use those specialized
   searches.
4. After exploring papers, report their similarity scores against the
   project's research questions.
5. Suggest adding highly relevant papers to the project.

## Response Format
- Present search results as a concise list with DOI, title, year, and citation
  count.
- When exploring a paper, highlight its relevance scores and key metadata.
- Always indicate whether a paper was already in the project graph.
- If no results are found, suggest alternative search strategies.
"""


def create_alrs_agent() -> LlmAgent:
    """Create and return the ALRS Agent instance.

    Returns:
        Configured LlmAgent for paper discovery.
    """
    return LlmAgent(
        name="ALRSAgent",
        model=_settings.adk_model_name,
        description=(
            "Handles academic paper discovery through OpenAlex searches "
            "(keyword, title, DOI, author, venue) and deep paper exploration "
            "with automatic embedding and citation graph construction."
        ),
        instruction=ALRS_AGENT_INSTRUCTION,
        tools=[
            search_papers_by_keyword,
            search_papers_by_title,
            search_papers_by_doi,
            search_papers_by_author,
            search_papers_by_venue,
            explore_paper,
            add_paper_to_project,
        ],
    )
