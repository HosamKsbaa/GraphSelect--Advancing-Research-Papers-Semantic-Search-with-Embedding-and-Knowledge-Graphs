"""Contract tests for `engines.citations` and `engines.collections`.

Ported from archive commit 865cd08 (`tests/test_ai_function_algorithms.py`
and `tests/test_assistant_functions.py`).
"""

from __future__ import annotations

import pytest

from engines.citations import (
    AnalysisFinding,
    LiteratureCandidate,
    available_sources,
    classify_candidate,
    format_apa,
    format_bibtex,
    resolve_reference,
    validate_sources,
)
from engines.collections import (
    InMemoryCollectionStore,
    ReviewProtocol,
    ReviewRecord,
    build_paper_collection,
    calculate_prisma_counts,
    collection_statistics,
    derive_decisions_from_records,
    validate_review_protocol,
)
from engines.papers import Author, Paper, Venue


def test_quote_verification_accepts_exact_spans_and_rejects_fabricated_quotes() -> None:
    paper = Paper(
        doi="10.48550/arxiv.1706.03762",
        title="Attention Is All You Need",
        abstract="We propose the Transformer. It relies entirely on self-attention.",
        authors=[Author(name="Ashish Vaswani"), Author(name="Noam Shazeer")],
        year=2017,
        venue=Venue(name="NeurIPS"),
    )
    collection = build_paper_collection(
        title="Transformer Collection",
        papers=[paper],
        research_questions=["How does the Transformer work?"],
    )
    store = InMemoryCollectionStore()
    store.save(collection)
    assert store.get(collection.collection_id).collection_hash == collection.collection_hash

    stats = collection_statistics(collection)
    assert stats.papers == 1 and stats.available_abstracts == 1

    entry = collection.entries[0]
    spans = available_sources(collection.collection_id, entry)
    assert len(spans) == 3  # Full abstract + 2 sentences

    valid_finding = AnalysisFinding(
        question="How does the Transformer work?",
        finding="It uses self-attention instead of recurrence.",
        sources=[spans[1]],
    )
    validated = validate_sources(collection, [valid_finding])
    assert validated[0].sources[0].doi == "10.48550/arxiv.1706.03762"

    # Tampering with quote text or character offsets must raise ValueError
    tampered = spans[1].model_copy(update={"quote": "It relies on recurrent neural networks."})
    with pytest.raises(ValueError, match="quote or character positions do not match"):
        validate_sources(
            collection,
            [
                AnalysisFinding(
                    question="How does the Transformer work?",
                    finding="Fabricated claim",
                    sources=[tampered],
                )
            ],
        )

    assert "@article{vaswani2017," in format_bibtex(paper)
    assert "Vaswani" in format_apa(paper)


def test_reference_resolution_and_candidate_classification() -> None:
    catalog = (
        ("10.1000/alpha", "Deep Residual Learning for Image Recognition"),
        ("10.1000/beta", "Attention Is All You Need"),
    )
    resolved_doi = resolve_reference("See (10.1000/alpha) for details.", catalog)
    assert resolved_doi.status == "resolved" and resolved_doi.canonical_doi == "10.1000/alpha"

    resolved_title = resolve_reference("Attention Is All You Need, 2017", catalog)
    assert resolved_title.status == "resolved" and resolved_title.canonical_doi == "10.1000/beta"

    unresolved = resolve_reference("10.1000/unknown", catalog)
    assert unresolved.status == "unresolved"

    # Candidate already cited
    cited_finding = classify_candidate(
        LiteratureCandidate(
            doi="10.1000/alpha",
            publication_date="2016-06-01",
            evidence_snippet="Residual connections ease optimization.",
        ),
        (resolved_doi,),
        cutoff_date="2020-01-01",
    )
    assert cited_finding.classification == "already_cited"

    # Candidate outside cutoff date
    after_cutoff = classify_candidate(
        LiteratureCandidate(
            doi="10.1000/gamma",
            publication_date="2023-05-01",
            evidence_snippet="New result.",
        ),
        (resolved_doi,),
        cutoff_date="2020-01-01",
    )
    assert after_cutoff.classification == "outside_cutoff"

    # Relevant missing candidate with evidence
    missing = classify_candidate(
        LiteratureCandidate(
            doi="10.1000/delta",
            publication_date="2018-05-01",
            evidence_snippet="Provides direct ablation benchmark.",
        ),
        (resolved_doi,),
        cutoff_date="2020-01-01",
    )
    assert missing.classification == "candidate_missing"


def test_prisma_flow_counts_and_protocol_locking() -> None:
    protocol = ReviewProtocol(
        protocol_id="proto_1",
        inclusion_criteria=["Empirical evaluation on citation graphs"],
    )
    assert validate_review_protocol(protocol) is True
    protocol.lock_protocol()
    with pytest.raises(ValueError, match="locked"):
        protocol.mutate_criteria(["New criterion"])
    v2 = protocol.create_new_version(["Updated criterion"])
    assert v2.version == 2 and not v2.is_locked

    records = (
        ReviewRecord(record_id="r1", disposition="included", study_id="s1"),
        ReviewRecord(record_id="r2", disposition="duplicate", duplicate_of="r1"),
        ReviewRecord(
            record_id="r3", disposition="excluded_title", reason="Off-topic title"
        ),
        ReviewRecord(
            record_id="r4", disposition="excluded_fulltext", reason="No empirical baseline"
        ),
    )
    counts = calculate_prisma_counts(records)
    assert counts.identified == 4
    assert counts.duplicates == 1
    assert counts.screened == 3
    assert counts.excluded_title == 1
    assert counts.reports_sought == 2
    assert counts.reports_assessed == 2
    assert counts.excluded_fulltext == 1
    assert counts.reports_included == 1
    assert counts.studies_included == 1

    decisions = derive_decisions_from_records(records)
    assert len(decisions) == 3
