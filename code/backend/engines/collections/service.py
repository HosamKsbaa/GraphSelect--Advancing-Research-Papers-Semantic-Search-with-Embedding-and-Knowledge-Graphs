"""Collection snapshot builder, PRISMA 2020 flow math, and in-memory store.

Ported from archive commit 865cd08 (`code/backend/ai/library/models.py`,
`code/backend/ai/library/service.py`, and
`code/backend/ai/functions/systematic_review/tools/tools.py`).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID, uuid4, uuid5

from engines.papers import CitationEdge, Paper

from .models import (
    CollectionEntry,
    CollectionStatistics,
    PaperCollection,
    PrismaCounts,
    ReviewProtocol,
    ReviewRecord,
    ScreeningDecision,
    content_hash,
)


def snapshot_entry(collection_id: UUID, paper: Paper) -> CollectionEntry:
    return CollectionEntry(
        entry_id=uuid5(collection_id, paper.paper_key),
        paper=paper,
        abstract_hash=content_hash(paper.abstract) if paper.abstract is not None else None,
        metadata_hash=content_hash(paper.model_dump_json()),
    )


def build_paper_collection(
    title: str,
    papers: Sequence[Paper],
    research_questions: list[str] | None = None,
    citation_edges: list[CitationEdge] | None = None,
    collection_id: UUID | None = None,
) -> PaperCollection:
    cid = collection_id or uuid4()
    entries = [snapshot_entry(cid, paper) for paper in papers]
    draft = PaperCollection(
        collection_id=cid,
        title=title,
        research_questions=list(research_questions or []),
        entries=entries,
        citation_edges=list(citation_edges or []),
    )
    body = draft.model_dump(mode="json", exclude={"collection_hash"})
    digest = content_hash(json.dumps(body, sort_keys=True, separators=(",", ":")))
    return draft.model_copy(update={"collection_hash": digest})


def collection_statistics(collection: PaperCollection) -> CollectionStatistics:
    years: dict[str, int] = {}
    available = 0
    for entry in collection.entries:
        if entry.paper.abstract and entry.paper.abstract.strip():
            available += 1
        year = str(entry.paper.year) if entry.paper.year is not None else "unknown"
        years[year] = years.get(year, 0) + 1
    return CollectionStatistics(
        papers=len(collection.entries),
        available_abstracts=available,
        missing_abstracts=len(collection.entries) - available,
        publication_years=years,
    )


def validate_review_protocol(protocol: ReviewProtocol) -> bool:
    """Validate systematic review protocol before screening."""
    if not protocol.inclusion_criteria:
        raise ValueError("Review protocol must specify at least one inclusion criterion")
    return True


def calculate_prisma_counts(records: tuple[ReviewRecord, ...]) -> PrismaCounts:
    """Calculate balanced PRISMA 2020 flow counts from verified review decisions."""
    seen_ids: set[str] = set()
    for r in records:
        if r.record_id in seen_ids:
            raise ValueError(f"Duplicate record ID found: {r.record_id}")
        seen_ids.add(r.record_id)

    by_id = {r.record_id: r for r in records}
    for r in records:
        if r.disposition == "pending":
            raise ValueError("Final counts need completed screening decisions")
        if r.duplicate_of:
            original = by_id.get(r.duplicate_of)
            if original is None or original.disposition == "duplicate":
                raise ValueError("Duplicate must point to a retained original record")

    identified = len(records)
    duplicates = sum(1 for r in records if r.disposition == "duplicate")
    screened = identified - duplicates
    excluded_title = sum(1 for r in records if r.disposition == "excluded_title")
    reports_sought = screened - excluded_title
    unavailable = sum(1 for r in records if r.disposition == "unavailable")
    reports_assessed = reports_sought - unavailable
    excluded_fulltext = sum(1 for r in records if r.disposition == "excluded_fulltext")
    reports_included = sum(1 for r in records if r.disposition == "included")
    studies_included = len(
        {r.study_id for r in records if r.disposition == "included" and r.study_id}
    )
    return PrismaCounts(
        identified=identified,
        duplicates=duplicates,
        screened=screened,
        excluded_title=excluded_title,
        reports_sought=reports_sought,
        unavailable=unavailable,
        reports_assessed=reports_assessed,
        excluded_fulltext=excluded_fulltext,
        reports_included=reports_included,
        studies_included=studies_included,
    )


def derive_decisions_from_records(
    records: Sequence[ReviewRecord],
    protocol_version: int = 1,
) -> list[ScreeningDecision]:
    """Derive granular audit screening decisions from review records."""
    decisions: list[ScreeningDecision] = []
    for r in records:
        if r.disposition == "excluded_title":
            decisions.append(
                ScreeningDecision(
                    record_id=r.record_id,
                    stage="title_abstract",
                    decision="exclude",
                    reason=r.reason,
                    protocol_version=protocol_version,
                )
            )
        elif r.disposition == "excluded_fulltext":
            decisions.append(
                ScreeningDecision(
                    record_id=r.record_id,
                    stage="full_text",
                    decision="exclude",
                    reason=r.reason,
                    protocol_version=protocol_version,
                )
            )
        elif r.disposition == "included":
            decisions.append(
                ScreeningDecision(
                    record_id=r.record_id,
                    stage="full_text",
                    decision="include",
                    protocol_version=protocol_version,
                )
            )
        elif r.disposition == "pending":
            decisions.append(
                ScreeningDecision(
                    record_id=r.record_id,
                    stage="title_abstract",
                    decision="uncertain",
                    protocol_version=protocol_version,
                )
            )
    return decisions


class InMemoryCollectionStore:
    """In-memory collection store for M1 (swappable with Neo4j in M2)."""

    def __init__(self) -> None:
        self._collections: dict[UUID, PaperCollection] = {}

    def save(self, collection: PaperCollection) -> PaperCollection:
        collection.verify_hash()
        self._collections[collection.collection_id] = collection
        return collection

    def get(self, collection_id: UUID) -> PaperCollection:
        if collection_id not in self._collections:
            raise KeyError(f"Collection '{collection_id}' not found")
        collection = self._collections[collection_id]
        collection.verify_hash()
        return collection

    def list_all(self) -> list[PaperCollection]:
        return list(self._collections.values())
