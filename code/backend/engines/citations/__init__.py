"""Public interface for the citations verification and formatting engine."""

from .models import (
    AnalysisFinding,
    AuditFinding,
    LiteratureCandidate,
    PaperSourceReference,
    ReferenceMatch,
    content_hash,
)
from .service import (
    available_sources,
    classify_candidate,
    format_apa,
    format_bibtex,
    resolve_reference,
    validate_sources,
)

__all__ = [
    "AnalysisFinding",
    "AuditFinding",
    "LiteratureCandidate",
    "PaperSourceReference",
    "ReferenceMatch",
    "available_sources",
    "classify_candidate",
    "content_hash",
    "format_apa",
    "format_bibtex",
    "resolve_reference",
    "validate_sources",
]
