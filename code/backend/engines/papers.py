"""Shared paper and citation records used by every engine.

Ported from the audited archive (`alrs_tool/paper_identity.py` and `alrs_tool/models.py`,
commit 865cd08). `PaperCreate` is renamed `Paper` because these engines have no database
create step; field names and validation rules are unchanged.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


def missing_corpus_id(value: int | None) -> bool:
    return value is None


class PaperIdentity(BaseModel):
    """A paper is keyed by its DOI, or by a verified Semantic Scholar Corpus ID when no DOI exists."""

    doi: str | None = None
    # Omit the absent field so legacy immutable snapshots keep their original hash.
    corpus_id: int | None = Field(default=None, gt=0, strict=True, exclude_if=missing_corpus_id)

    @field_validator("doi", mode="before")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        if not cleaned or cleaned.startswith("corpusid:"):
            raise ValueError("Store a Corpus ID separately from the DOI")
        return cleaned

    @model_validator(mode="after")
    def require_identifier(self) -> Self:
        if self.doi is None and self.corpus_id is None:
            raise ValueError("A paper needs a DOI or a verified Semantic Scholar Corpus ID")
        return self

    @property
    def paper_key(self) -> str:
        if self.doi is not None:
            return self.doi
        return f"CorpusId:{self.corpus_id}"


def identity_from_key(key: str) -> PaperIdentity:
    if key.startswith("CorpusId:"):
        return PaperIdentity(corpus_id=int(key.removeprefix("CorpusId:")))
    return PaperIdentity(doi=key)


class RetractionStatus(str, Enum):
    RETRACTED = "retracted"
    CORRECTED = "corrected"
    EXPRESSION_OF_CONCERN = "concern"
    NO_NOTICE_FOUND = "no_notice_found"
    UNKNOWN = "unknown"


class Author(BaseModel):
    name: str
    affiliation: str | None = None
    openalex_id: str | None = None


class Venue(BaseModel):
    name: str
    issn: str | None = None
    openalex_id: str | None = None
    is_oa: bool | None = None


class DatedCitationCount(BaseModel):
    observed_at: datetime
    citation_count: int
    source_version: str | None = None


class Paper(PaperIdentity):
    title: str
    abstract: str | None = None
    year: int | None = None
    authors: list[Author] = Field(default_factory=list)
    venue: Venue | None = None
    citation_count: int | None = Field(default=None, ge=0)
    retrieved_at: datetime | None = None
    dated_citations: list[DatedCitationCount] = Field(default_factory=list)
    retraction_status: RetractionStatus = RetractionStatus.UNKNOWN
    is_retracted: bool | None = None  # None means unknown, never silently false
    topics: list[str] = Field(default_factory=list)
    openalex_id: str | None = None


class CitationEdge(BaseModel):
    """The source paper cites the target paper."""

    source_doi: str | None = None
    target_doi: str | None = None
    source_corpus_id: int | None = Field(default=None, gt=0, strict=True, exclude_if=missing_corpus_id)
    target_corpus_id: int | None = Field(default=None, gt=0, strict=True, exclude_if=missing_corpus_id)
    direction: str = "cites"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_receipt_id: str | None = None

    @field_validator("source_doi", "target_doi", mode="before")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):]
        return cleaned.strip().lower()

    @model_validator(mode="after")
    def require_endpoints(self) -> Self:
        PaperIdentity(doi=self.source_doi, corpus_id=self.source_corpus_id)
        PaperIdentity(doi=self.target_doi, corpus_id=self.target_corpus_id)
        return self

    @property
    def source_key(self) -> str:
        return PaperIdentity(doi=self.source_doi, corpus_id=self.source_corpus_id).paper_key

    @property
    def target_key(self) -> str:
        return PaperIdentity(doi=self.target_doi, corpus_id=self.target_corpus_id).paper_key
