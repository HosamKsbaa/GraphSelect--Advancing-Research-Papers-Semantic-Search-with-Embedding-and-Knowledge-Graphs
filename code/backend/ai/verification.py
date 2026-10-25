"""Citation verification gate (`verify_citations`) for the ALRS Research Agent (M2).

Ensures that every bracketed `[10.xxxx/...]` DOI in a synthesized review exists in the
saved `PaperCollection` and that any `AnalysisFinding` quotes match exact abstract spans.
Invented or unsupported DOIs are stripped and reported in `VerificationReport`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from engines.citations import AnalysisFinding, validate_sources
from engines.collections import PaperCollection

from .tools import WriteReviewOutput

_BRACKETED_DOI_RE = re.compile(r"\[(10\.\d{4,9}/[^\s\[\]]+)\]", flags=re.IGNORECASE)


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    verified: bool
    verified_dois: list[str] = Field(default_factory=list)
    unsupported_dois: list[str] = Field(default_factory=list)
    cleaned_markdown: str
    verified_findings_count: int = 0


def verify_review_citations(
    collection: PaperCollection,
    review_output: WriteReviewOutput,
    findings: list[AnalysisFinding] | None = None,
) -> VerificationReport:
    """Verify all inline `[DOI]` citations and optional `AnalysisFinding` spans against `collection`."""
    verified_findings_count = review_output.verified_findings_count
    if findings is not None:
        validated_findings = validate_sources(collection, findings)
        verified_findings_count = len(validated_findings)

    allowed_dois: dict[str, str] = {}
    for entry in collection.entries:
        if entry.paper.doi:
            allowed_dois[entry.paper.doi.strip().lower()] = entry.paper.doi

    verified_dois: list[str] = []
    unsupported_dois: list[str] = []

    for declared_doi in review_output.cited_dois:
        key = declared_doi.strip().lower()
        if key in allowed_dois:
            canonical = allowed_dois[key]
            if canonical not in verified_dois:
                verified_dois.append(canonical)
        else:
            if declared_doi not in unsupported_dois:
                unsupported_dois.append(declared_doi)

    def _replace_match(match: re.Match[str]) -> str:
        raw_doi = match.group(1).strip()
        key = raw_doi.lower()
        if key in allowed_dois:
            canonical = allowed_dois[key]
            if canonical not in verified_dois:
                verified_dois.append(canonical)
            return f"[{canonical}]"
        if raw_doi not in unsupported_dois:
            unsupported_dois.append(raw_doi)
        return ""

    cleaned = _BRACKETED_DOI_RE.sub(_replace_match, review_output.markdown_review)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()

    is_verified = len(unsupported_dois) == 0 and len(verified_dois) > 0
    return VerificationReport(
        collection_id=str(collection.collection_id),
        verified=is_verified,
        verified_dois=verified_dois,
        unsupported_dois=unsupported_dois,
        cleaned_markdown=cleaned,
        verified_findings_count=verified_findings_count,
    )
