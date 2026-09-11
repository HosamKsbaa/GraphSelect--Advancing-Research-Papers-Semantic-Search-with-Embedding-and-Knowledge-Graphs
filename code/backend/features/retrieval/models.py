"""Paper, Author, Venue, and Keyword Pydantic models for ALRS v2.

Canonical location under the feature-based architecture.  Previously
``models/paper.py`` in the layer-based layout.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

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
    referenced_works: list[str] = Field(default_factory=list)
    authors: list[AuthorCreate] = Field(default_factory=list)
    venue: VenueCreate | None = None

    @field_validator('authors', mode='before')
    @classmethod
    def parse_authors(cls, v: Any) -> list[AuthorCreate]:
        if not v:
            return []
        result: list[AuthorCreate] = []
        for item in v:
            if isinstance(item, str):
                result.append(AuthorCreate(name=item.strip()))
            elif isinstance(item, dict):
                result.append(AuthorCreate(**item))
            elif isinstance(item, AuthorCreate):
                result.append(item)
        return result

    @field_validator('venue', mode='before')
    @classmethod
    def parse_venue(cls, v: Any) -> VenueCreate | None:
        if not v:
            return None
        if isinstance(v, str):
            return VenueCreate(name=v.strip())
        if isinstance(v, dict):
            return VenueCreate(**v)
        if isinstance(v, VenueCreate):
            return v
        return None


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
    is_stub: bool = False
    is_bridge: bool = False
    can_expand_deeply: bool = True
    is_retracted: bool = False


class PaperSummary(BaseModel):
    """Lightweight paper summary for candidate lists."""

    doi: str
    title: str
    year: int | None = None
    cited_by_count: int = 0
    authors: list[str] = Field(default_factory=list)
