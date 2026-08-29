from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    SEARCH_STARTED = 'search_started'
    LEVEL_COMPLETE = 'level_complete'
    EMBEDDING_PROGRESS = 'embedding_progress'
    CYCLE_RESULTS = 'cycle_results'
    RANKING_COMPLETE = 'ranking_complete'
    SEARCH_COMPLETE = 'search_complete'
    ERROR_RECOVERED = 'error_recovered'
    SEARCH_FAILED = 'search_failed'
    THROTTLED = 'throttled'
    ENQUEUE_CONFIRMATION = 'enqueue_confirmation'


class ProgressEvent(BaseModel):
    event_type: EventType
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    progress_percent: float = Field(ge=0.0, le=100.0)
    message: str
    data: dict[str, object] | None = None


class CycleResultsData(BaseModel):
    level: int
    papers_discovered: int
    papers_new: int
    top_papers: list[dict[str, object]] = Field(default_factory=list)


class ThrottledData(BaseModel):
    service: str
    old_rate: float
    new_rate: float
    retry_after_seconds: float | None = None


class CandidatePaperState(BaseModel):
    """Rich state payload for a candidate paper discovered during 1-hop traversal."""

    doi: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract_snippet: str = ""
    direction: str = "forward_citation"  # 'forward_citation' | 'backward_reference' | 'both'
    citation_count: int = 0
    in_graph_degree: int = 0
    similarity_scores: list[dict[str, Any]] = Field(default_factory=list)
    max_similarity: float = 0.0
    mean_similarity: float = 0.0
    already_in_library: bool = False
    embedding_cached: bool = True
    pagerank_score: float = 0.0
    partition: str | None = None  # 'foundational_prior_art' | 'contemporary_breakthroughs' | 'topological_bridges'
    archetype_scores: dict[str, float] = Field(default_factory=dict)
    recommendation_rationale: str = ""
    primary_rq: str = ""


class OneHopExpansionResult(BaseModel):
    """Result of a bounded 1-hop GraphSelect traversal cycle."""

    seed_doi: str
    seed_title: str
    cycle_level: int = 1
    total_discovered: int = 0
    total_new: int = 0
    forward_count: int = 0
    backward_count: int = 0
    both_count: int = 0
    candidates: list[CandidatePaperState] = Field(default_factory=list)
    new_dois: list[str] = Field(default_factory=list)
    traversal_summary: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def level(self) -> int:
        return self.cycle_level

    @property
    def papers_discovered(self) -> int:
        return self.total_discovered

    @property
    def papers_new(self) -> int:
        return self.total_new


