from __future__ import annotations

from datetime import datetime
from enum import Enum

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
