"""Deterministic quote verification, reference resolution, and citation export.

Ported from archive commit 865cd08 (`code/backend/ai/library/models.py`,
`code/backend/ai/functions/paper_analysis/service.py`, and
`code/backend/ai/functions/dissertation_audit/tools/tools.py`).
"""

from __future__ import annotations

import datetime
import hashlib
import re
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from engines.papers import Paper

from .models import (
    AnalysisFinding,
    AuditFinding,
    LiteratureCandidate,
    PaperSourceReference,
    ReferenceMatch,
)


class EntryLike(Protocol):
    @property
    def entry_id(self) -> UUID: ...

    @property
    def paper(self) -> Paper: ...

    @property
    def abstract_hash(self) -> str | None: ...


class CollectionLike(Protocol):
    @property
    def collection_id(self) -> UUID: ...

    @property
    def entries(self) -> Sequence[EntryLike]: ...


def available_sources(collection_id: UUID, entry: EntryLike) -> list[PaperSourceReference]:
    """Split a saved abstract into exact sentence spans with SHA-256 hash verification."""
    abstract = entry.paper.abstract
    if not abstract or not abstract.strip():
        return []
    if entry.abstract_hash is None:
        raise ValueError("The saved abstract is missing its source hash")
    spans = [(0, len(abstract))]
    for passage in re.finditer(r"\S.*?(?:[.!?。！？](?=\s|$)|\Z)", abstract, re.DOTALL):
        if passage.span() != spans[0]:
            spans.append(passage.span())
    return [
        PaperSourceReference(
            collection_id=collection_id,
            entry_id=entry.entry_id,
            abstract_hash=entry.abstract_hash,
            title=entry.paper.title,
            doi=entry.paper.doi,
            corpus_id=entry.paper.corpus_id,
            quote=abstract[start:end],
            start=start,
            end=end,
        )
        for start, end in spans
    ]


def validate_sources(
    collection: CollectionLike,
    findings: list[AnalysisFinding],
) -> list[AnalysisFinding]:
    """Verify every quote, character span, hash, and DOI cited by an LLM against saved abstracts."""
    entries = {entry.entry_id: entry for entry in collection.entries}
    for finding in findings:
        for source in finding.sources:
            entry = entries.get(source.entry_id)
            if source.collection_id != collection.collection_id or entry is None:
                raise ValueError("The AI cited a paper outside the selected collection")
            abstract = entry.paper.abstract
            if abstract is None or entry.abstract_hash != source.abstract_hash:
                raise ValueError("The AI citation does not match the saved abstract")
            if (
                source.end <= source.start
                or source.end > len(abstract)
                or abstract[source.start : source.end] != source.quote
            ):
                raise ValueError(
                    "The AI quote or character positions do not match the saved abstract"
                )
            source.title, source.doi = entry.paper.title, entry.paper.doi
            source.corpus_id = entry.paper.corpus_id
    return findings


def resolve_reference(
    raw_text: str,
    catalog: tuple[tuple[str, str], ...],
) -> ReferenceMatch:
    """Resolve a raw citation reference against a catalog of (doi, title)."""
    norm_text = raw_text.strip().lower()
    catalog_map = {doi.strip().lower(): title for doi, title in catalog}

    for part in raw_text.split():
        cleaned = part.strip("()[]<>,.;:\"'").lower()
        if cleaned.startswith("10.") and "/" in cleaned:
            if cleaned in catalog_map:
                return ReferenceMatch(
                    reference_id=f"ref_{cleaned}",
                    raw_text=raw_text,
                    canonical_doi=cleaned,
                    status="resolved",
                    candidate_dois=[cleaned],
                )
            return ReferenceMatch(
                reference_id=f"ref_{cleaned}",
                raw_text=raw_text,
                canonical_doi=None,
                status="unresolved",
                candidate_dois=[],
            )

    matches = [
        doi
        for doi, title in catalog
        if title.lower() in norm_text or norm_text in title.lower()
    ]
    if len(matches) == 1:
        return ReferenceMatch(
            reference_id=f"ref_{matches[0]}",
            raw_text=raw_text,
            canonical_doi=matches[0],
            status="resolved",
            candidate_dois=matches,
        )
    if len(matches) > 1:
        return ReferenceMatch(
            reference_id="ref_ambiguous",
            raw_text=raw_text,
            status="ambiguous",
            candidate_dois=sorted(matches),
        )
    return ReferenceMatch(
        reference_id="ref_unresolved",
        raw_text=raw_text,
        status="unresolved",
    )


def classify_candidate(
    candidate: LiteratureCandidate,
    references: tuple[ReferenceMatch, ...],
    cutoff_date: str | None = None,
    section_id: str = "main",
    manuscript_hash: str = "v1",
) -> AuditFinding:
    """Classify a literature candidate with validated date parsing, relevance, and evidence checks."""
    cand_doi = candidate.doi.strip().lower()
    finding_id = hashlib.sha256(
        f"{manuscript_hash}:{section_id}:{cand_doi}".encode()
    ).hexdigest()[:16]

    for ref in references:
        if ref.canonical_doi and ref.canonical_doi.strip().lower() == cand_doi:
            return AuditFinding(
                finding_id=finding_id,
                candidate_doi=candidate.doi,
                section_id=section_id,
                manuscript_hash=manuscript_hash,
                classification="already_cited",
                reason=f"Candidate DOI matches cited reference {ref.reference_id}",
            )

    if any(
        r.status == "ambiguous" and cand_doi in [c.lower() for c in r.candidate_dois]
        for r in references
    ):
        return AuditFinding(
            finding_id=finding_id,
            candidate_doi=candidate.doi,
            section_id=section_id,
            manuscript_hash=manuscript_hash,
            classification="ambiguous_skip",
            reason="Candidate DOI is a candidate in an ambiguous manuscript reference",
        )

    if candidate.publication_date:
        try:
            cand_d = datetime.date.fromisoformat(candidate.publication_date[:10])
            if cutoff_date:
                try:
                    cutoff_d = datetime.date.fromisoformat(cutoff_date[:10])
                    if cand_d > cutoff_d:
                        return AuditFinding(
                            finding_id=finding_id,
                            candidate_doi=candidate.doi,
                            section_id=section_id,
                            manuscript_hash=manuscript_hash,
                            classification="outside_cutoff",
                            reason=f"Candidate date {cand_d} is after validated cutoff {cutoff_d}",
                        )
                except ValueError:
                    pass
        except ValueError:
            return AuditFinding(
                finding_id=finding_id,
                candidate_doi=candidate.doi,
                section_id=section_id,
                manuscript_hash=manuscript_hash,
                classification="unknown_date",
                reason=f"Invalid publication date format: {candidate.publication_date}",
            )
    elif cutoff_date:
        return AuditFinding(
            finding_id=finding_id,
            candidate_doi=candidate.doi,
            section_id=section_id,
            manuscript_hash=manuscript_hash,
            classification="unknown_date",
            reason="Missing publication date when cutoff is active",
        )

    if not candidate.is_relevant or candidate.relevance_score < 0.5:
        return AuditFinding(
            finding_id=finding_id,
            candidate_doi=candidate.doi,
            section_id=section_id,
            manuscript_hash=manuscript_hash,
            classification="irrelevant",
            reason="Candidate below relevance threshold",
        )

    if not candidate.evidence_snippet.strip():
        return AuditFinding(
            finding_id=finding_id,
            candidate_doi=candidate.doi,
            section_id=section_id,
            manuscript_hash=manuscript_hash,
            classification="missing_evidence",
            reason="Relevant candidate lacks supporting passage evidence",
        )

    return AuditFinding(
        finding_id=finding_id,
        candidate_doi=candidate.doi,
        section_id=section_id,
        manuscript_hash=manuscript_hash,
        classification="candidate_missing",
        reason="Relevant, in-cutoff candidate with evidence is absent from manuscript references",
        passage_evidence=candidate.evidence_snippet,
    )


def format_bibtex(paper: Paper) -> str:
    """Format a Paper as a deterministic BibTeX @article entry."""
    first_author = (paper.authors[0].name.split()[-1] if paper.authors else "paper").lower()
    clean_author = re.sub(r"[^a-z0-9]", "", first_author) or "paper"
    year_str = str(paper.year) if paper.year is not None else "nd"
    cite_key = f"{clean_author}{year_str}"
    authors_bib = " and ".join(a.name for a in paper.authors) if paper.authors else "Unknown"
    fields = [
        f"  author = {{{authors_bib}}}",
        f"  title = {{{paper.title}}}",
    ]
    if paper.year is not None:
        fields.append(f"  year = {{{paper.year}}}")
    if paper.venue and paper.venue.name:
        fields.append(f"  journal = {{{paper.venue.name}}}")
    if paper.doi:
        fields.append(f"  doi = {{{paper.doi}}}")
    body = ",\n".join(fields)
    return f"@article{{{cite_key},\n{body}\n}}"


def format_apa(paper: Paper) -> str:
    """Format a Paper as a deterministic APA-style reference string."""
    authors = ", ".join(a.name for a in paper.authors) if paper.authors else "Unknown"
    year = f"({paper.year})." if paper.year is not None else "(n.d.)."
    venue = f" {paper.venue.name}." if (paper.venue and paper.venue.name) else ""
    doi = f" https://doi.org/{paper.doi}" if paper.doi else ""
    return f"{authors} {year} {paper.title}.{venue}{doi}"
