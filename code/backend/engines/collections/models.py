"""Models for immutable paper collections and PRISMA 2020 screening flows.

Ported from archive commit 865cd08 (`code/backend/ai/library/models.py` and
`code/backend/ai/functions/systematic_review/models.py`).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from engines.papers import CitationEdge, Paper


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


Disposition = Literal[
    "duplicate",
    "excluded_title",
    "unavailable",
    "excluded_fulltext",
    "included",
    "pending",
]


class CollectionEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: UUID
    paper: Paper
    abstract_hash: str | None
    metadata_hash: str


class CollectionStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: int
    available_abstracts: int
    missing_abstracts: int
    publication_years: dict[str, int] = Field(default_factory=dict)


class PaperCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    collection_id: UUID = Field(default_factory=uuid4)
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    research_questions: list[str] = Field(default_factory=list)
    search_settings: dict[str, JsonValue] = Field(default_factory=dict)
    entries: list[CollectionEntry] = Field(default_factory=list)
    citation_edges: list[CitationEdge] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    collection_hash: str = ""

    def verify_hash(self) -> None:
        body = self.model_dump(mode="json", exclude={"collection_hash"})
        expected = content_hash(json.dumps(body, sort_keys=True, separators=(",", ":")))
        if expected != self.collection_hash:
            raise ValueError("The saved paper collection changed; its original snapshot is required")


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    disposition: Disposition
    duplicate_of: str | None = None
    study_id: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if (self.disposition == "duplicate") != bool(self.duplicate_of):
            raise ValueError("Only a duplicate requires duplicate_of")
        if (self.disposition == "included") != bool(self.study_id):
            raise ValueError("Only an included report requires study_id")
        if self.disposition.startswith("excluded") and not self.reason:
            raise ValueError("An exclusion needs a reason")
        return self


class PrismaCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identified: int
    duplicates: int
    screened: int
    excluded_title: int
    reports_sought: int
    unavailable: int
    reports_assessed: int
    excluded_fulltext: int
    reports_included: int
    studies_included: int


class ReviewProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str
    version: int = 1
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    date_range: tuple[str, str] | None = None
    study_types: list[str] = Field(default_factory=list)
    is_locked: bool = False
    rescreen_required: bool = False

    def lock_protocol(self) -> None:
        self.is_locked = True

    def mutate_criteria(
        self,
        new_inclusion: list[str],
        new_exclusion: list[str] | None = None,
    ) -> None:
        if self.is_locked:
            raise ValueError(
                "Protocol is locked against modification. Create a new version instead."
            )
        self.inclusion_criteria = list(new_inclusion)
        if new_exclusion is not None:
            self.exclusion_criteria = list(new_exclusion)

    def create_new_version(
        self,
        new_inclusion: list[str] | None = None,
        new_exclusion: list[str] | None = None,
        rescreen: bool = True,
    ) -> ReviewProtocol:
        return ReviewProtocol(
            protocol_id=self.protocol_id,
            version=self.version + 1,
            inclusion_criteria=list(new_inclusion)
            if new_inclusion is not None
            else list(self.inclusion_criteria),
            exclusion_criteria=list(new_exclusion)
            if new_exclusion is not None
            else list(self.exclusion_criteria),
            date_range=self.date_range,
            study_types=list(self.study_types),
            is_locked=False,
            rescreen_required=rescreen,
        )


class ScreeningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    stage: Literal["title_abstract", "full_text"]
    decision: Literal["include", "exclude", "uncertain"]
    protocol_version: int = 1
    reason: str | None = None
    reviewer: str = "ai_screening_subagent"
