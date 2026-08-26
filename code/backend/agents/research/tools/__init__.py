"""Research agent tools sub-package."""
from __future__ import annotations

from agents.research.tools.analysis_tools import (
    analyze_coverage,
    compute_similarity,
    extract_paper_findings,
    generate_comparison_matrix,
    get_citation_stats,
    rank_papers,
    suggest_gap_queries,
    synthesize_evidence,
)
from agents.research.tools.retrieval_tools import (
    add_paper_to_project,
    explore_paper,
    get_project_papers,
)
from agents.research.tools.search_tools import (
    add_research_question,
    get_top_authors,
    get_top_venues,
    list_research_questions,
    search_papers_by_author,
    search_papers_by_doi,
    search_papers_by_keyword,
    search_papers_by_title,
    search_papers_by_venue,
)

__all__ = [
    "search_papers_by_keyword",
    "search_papers_by_doi",
    "search_papers_by_title",
    "search_papers_by_author",
    "search_papers_by_venue",
    "add_research_question",
    "list_research_questions",
    "get_top_authors",
    "get_top_venues",
    "explore_paper",
    "add_paper_to_project",
    "get_project_papers",
    "compute_similarity",
    "get_citation_stats",
    "analyze_coverage",
    "suggest_gap_queries",
    "rank_papers",
    "extract_paper_findings",
    "generate_comparison_matrix",
    "synthesize_evidence",
]
