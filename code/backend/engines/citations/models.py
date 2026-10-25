"""Models for exact quote verification, reference resolution, and citation formatting.

Ported from archive commit 865cd08 (`code/backend/ai/library/models.py` and
`code/backend/ai/functions/dissertation_audit/models.py`).
"""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from engines.papers import missing_corpus_id


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PaperSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: UUID
    entry_id: UUID
    abstract_hash: str
    title: str = ""
    doi: str | None = ""
    corpus_id: int | None = Field(default=None, exclude_if=missing_corpus_id)
    quote: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class AnalysisFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    finding: str = Field(min_length=1)
    sources: list[PaperSourceReference] = Field(min_length=1)


class ReferenceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str
    raw_text: str
    canonical_doi: str | None = None
    status: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"
    candidate_dois: list[str] = Field(default_factory=list)


class LiteratureCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doi: str
    title: str = ""
    publication_date: str | None = None  # YYYY-MM-DD
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    is_relevant: bool = True
    evidence_snippet: str = ""


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    candidate_doi: str
    section_id: str = "main"
    manuscript_hash: str = "v1"
    classification: Literal[
        "already_cited",
        "outside_cutoff",
        "candidate_missing",
        "ambiguous_skip",
        "missing_evidence",
        "irrelevant",
        "unknown_date",
    ]
    reason: str
    passage_evidence: str = ""
