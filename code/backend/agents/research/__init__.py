"""Research agent sub-package.

Contains the ResearchAgent (coordinator), ALRSAgent (search/discovery),
GapFinderAgent (analysis/ranking), EvidenceSynthesizerAgent (synthesis/matrices),
and their shared tool functions and data models.
"""
from __future__ import annotations

from agents.research.agent import ResearchAgent, create_research_agent
from agents.research.alrs_agent import create_alrs_agent
from agents.research.evidence_synthesizer import (
    create_evidence_synthesizer_agent,
    evidence_synthesizer_agent,
)
from agents.research.gap_finder import create_gap_finder_agent
from agents.research.models import (
    ComparisonDimension,
    PaperFinding,
    StructuredComparisonMatrix,
)

__all__ = [
    "ResearchAgent",
    "create_research_agent",
    "create_alrs_agent",
    "create_gap_finder_agent",
    "create_evidence_synthesizer_agent",
    "evidence_synthesizer_agent",
    "PaperFinding",
    "ComparisonDimension",
    "StructuredComparisonMatrix",
]
