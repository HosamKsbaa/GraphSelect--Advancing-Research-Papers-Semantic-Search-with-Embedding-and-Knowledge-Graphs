from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AuthorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    openalex_id: str | None = None
    orcid: str | None = None
    institution: str | None = None


class AuthorRead(BaseModel):
    name: str
    openalex_id: str | None = None
    orcid: str | None = None
    institution: str | None = None
    paper_count: int = 0


class VenueCreate(BaseModel):
    name: str = Field(..., min_length=1)
    openalex_id: str | None = None
    issn: str | None = None
    venue_type: str | None = None


class VenueRead(BaseModel):
    name: str
    openalex_id: str | None = None
    issn: str | None = None
    venue_type: str | None = None
    paper_count: int = 0


class KeywordCreate(BaseModel):
    term: str = Field(..., min_length=1)


class PaperCreate(BaseModel):
    doi: str = Field(..., pattern=r'^10\.\d{4,}/\S+$')
    title: str = Field(..., min_length=1)
    abstract: str | None = None
    year: int | None = None
    cited_by_count: int = 0
    openalex_id: str | None = None
    publication_date: str | None = None
    source: str = 'openalex'


class PaperRead(BaseModel):
    """Paper model for API responses. MUST NOT include embedding field (zero RAM policy)."""

    doi: str
    title: str
    abstract: str | None = None
    year: int | None = None
    cited_by_count: int = 0
    openalex_id: str | None = None
    publication_date: str | None = None
    source: str = 'openalex'
    authors: list[AuthorRead] = Field(default_factory=list)
    venue: VenueRead | None = None
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class PaperSummary(BaseModel):
    """Lightweight paper summary for candidate lists."""

    doi: str
    title: str
    year: int | None = None
    cited_by_count: int = 0
    authors: list[str] = Field(default_factory=list)
