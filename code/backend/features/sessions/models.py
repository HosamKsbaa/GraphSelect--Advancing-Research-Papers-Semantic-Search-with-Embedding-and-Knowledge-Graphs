from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SearchMode(str, Enum):
    INTERACTIVE = 'interactive'
    AUTOMATED = 'automated'


class SessionStatus(str, Enum):
    CREATED = 'created'
    RUNNING = 'running'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    FAILED = 'failed'


class SearchRequest(BaseModel):
    seed_doi: str | None = None
    seed_title: str | None = None
    research_questions: list[str] = Field(..., min_length=1, max_length=6)
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_depth: int = Field(default=2, ge=1, le=5)
    mode: SearchMode = SearchMode.INTERACTIVE

    @field_validator('research_questions')
    @classmethod
    def validate_questions(cls, v: list[str]) -> list[str]:
        if not all(q.strip() for q in v):
            raise ValueError('All research questions must be non-empty')
        return [q.strip() for q in v]

    @field_validator('seed_doi')
    @classmethod
    def validate_doi(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r'^10\.\d{4,}/\S+$', v):
            raise ValueError('Invalid DOI format. Expected: 10.XXXX/...')
        return v


class SearchResponse(BaseModel):
    session_id: str
    status: SessionStatus
    seed_paper_doi: str
    message: str


class SessionRead(BaseModel):
    session_id: str
    seed_doi: str
    research_questions: list[str]
    similarity_threshold: float
    max_depth: int
    mode: SearchMode
    status: SessionStatus
    papers_discovered: int = 0
    papers_relevant: int = 0
    current_depth: int = 0
    created_at: datetime
    updated_at: datetime | None = None


class SessionList(BaseModel):
    sessions: list[SessionRead]
    total: int
