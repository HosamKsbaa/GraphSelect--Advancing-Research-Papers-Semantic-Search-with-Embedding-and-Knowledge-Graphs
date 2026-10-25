"""Public interface for the paper collections and PRISMA screening engine."""

from .models import (
    CollectionEntry,
    CollectionStatistics,
    Disposition,
    PaperCollection,
    PrismaCounts,
    ReviewProtocol,
    ReviewRecord,
    ScreeningDecision,
    content_hash,
)
from .service import (
    InMemoryCollectionStore,
    build_paper_collection,
    calculate_prisma_counts,
    collection_statistics,
    derive_decisions_from_records,
    snapshot_entry,
    validate_review_protocol,
)

__all__ = [
    "CollectionEntry",
    "CollectionStatistics",
    "Disposition",
    "InMemoryCollectionStore",
    "PaperCollection",
    "PrismaCounts",
    "ReviewProtocol",
    "ReviewRecord",
    "ScreeningDecision",
    "build_paper_collection",
    "calculate_prisma_counts",
    "collection_statistics",
    "content_hash",
    "derive_decisions_from_records",
    "snapshot_entry",
    "validate_review_protocol",
]
