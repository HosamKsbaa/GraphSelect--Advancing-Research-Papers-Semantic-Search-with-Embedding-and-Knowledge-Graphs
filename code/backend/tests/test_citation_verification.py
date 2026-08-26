"""Unit and integration tests for Citation Hallucination Verification Engine.

Covers:
    - normalize_doi and extract_dois from diverse text structures
    - In-memory verify_citation_grounding (zero hallucination detection)
    - Database-backed CitationVerifier with mocked Neo4jService
    - WritingService.verify_citations endpoint/method
    - ReviewerAgent integration rejecting hallucinated citations
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.writing.citation_verifier import (
    CitationVerificationResult,
    CitationVerifier,
    extract_dois,
    normalize_doi,
    verify_citation_grounding,
)
from core.llm.models import CompletionResponse, TokenUsage
from features.writing.service import WritingService


# ============================================================================
# DOI Extraction & Normalization Tests
# ============================================================================

def test_normalize_doi():
    """Test DOI normalization to canonical lowercase without prefixes or trailing punctuation."""
    assert normalize_doi("10.1000/182") == "10.1000/182"
    assert normalize_doi("doi: 10.1000/182.") == "10.1000/182"
    assert normalize_doi("https://doi.org/10.1145/3308558.3313508") == "10.1145/3308558.3313508"
    assert normalize_doi("http://dx.doi.org/10.1000/AbC-123,") == "10.1000/abc-123"
    assert normalize_doi(" (DOI: 10.1000/XYZ) ") == "10.1000/xyz"
    assert normalize_doi("") == ""


def test_extract_dois_from_text():
    """Test extraction of multiple DOIs across mixed markdown and citation styles."""
    text = """
    We build upon prior work in graph transformers (10.1000/valid-1) and
    attention mechanisms (doi: 10.1000/VALID-2).
    See also https://doi.org/10.1000/valid-3 for additional details.
    Duplicate reference (10.1000/valid-1) should not be duplicated in results.
    """
    dois = extract_dois(text)

    assert len(dois) == 3
    assert "10.1000/valid-1" in dois
    assert "10.1000/valid-2" in dois
    assert "10.1000/valid-3" in dois


def test_extract_dois_empty_or_none():
    """Test extract_dois handles empty strings or texts without DOIs."""
    assert extract_dois("") == []
    assert extract_dois("No academic citations here.") == []


# ============================================================================
# In-Memory Citation Grounding Tests
# ============================================================================

def test_verify_citation_grounding_zero_hallucinations():
    """Test zero hallucination verification passes when all citations match known library."""
    known = {"10.1000/gt-1", "10.1000/gt-2", "10.1000/gt-3"}
    assigned = ["10.1000/gt-1", "10.1000/gt-2"]
    text = "We compare (DOI: 10.1000/gt-1) against baseline (DOI: 10.1000/gt-2)."

    res = verify_citation_grounding(text, known_dois=known, assigned_dois=assigned)

    assert res.is_grounded is True
    assert res.passed is True
    assert res.hallucination_rate == 0.0
    assert len(res.hallucinated_dois) == 0
    assert len(res.missing_assigned_dois) == 0
    assert res.coverage_rate == 1.0


def test_verify_citation_grounding_detects_hallucinations():
    """Test detection of fabricated / unverified DOIs."""
    known = {"10.1000/real-paper"}
    assigned = ["10.1000/real-paper"]
    text = "Grounded citation (10.1000/real-paper) and hallucinated citation (10.1000/fake-hallucination)."

    res = verify_citation_grounding(text, known_dois=known, assigned_dois=assigned)

    assert res.is_grounded is False
    assert res.passed is False
    assert "10.1000/fake-hallucination" in res.hallucinated_dois
    assert res.hallucination_rate == 0.5


def test_verify_citation_grounding_detects_missing_assigned():
    """Test detection of assigned papers that were omitted from the draft."""
    known = {"10.1000/paper-1", "10.1000/paper-2", "10.1000/paper-3"}
    assigned = ["10.1000/paper-1", "10.1000/paper-2"]
    text = "We only discuss (10.1000/paper-1) here."

    res = verify_citation_grounding(text, known_dois=known, assigned_dois=assigned)

    assert res.is_grounded is True
    assert res.passed is False
    assert res.missing_assigned_dois == ["10.1000/paper-2"]
    assert res.coverage_rate == 0.5


# ============================================================================
# Database-Backed CitationVerifier Tests
# ============================================================================

@pytest.mark.asyncio
async def test_citation_verifier_with_neo4j():
    """Test CitationVerifier queries Neo4j for paper verification."""
    mock_neo4j = AsyncMock()

    async def mock_get_paper(doi):
        if doi == "10.1000/verified":
            return {"doi": "10.1000/verified", "title": "Verified Paper", "year": 2024}
        return None

    mock_neo4j.get_paper_by_doi.side_effect = mock_get_paper

    verifier = CitationVerifier(mock_neo4j)
    draft_text = "According to (10.1000/verified) and fabricated (10.1000/fabricated)."

    res = await verifier.verify_text_citations(
        text=draft_text,
        project_id="proj-1",
        assigned_dois=["10.1000/verified"],
    )

    assert res.is_grounded is False
    assert "10.1000/fabricated" in res.hallucinated_dois
    assert "10.1000/verified" in res.verified_dois
    assert res.passed is False


# ============================================================================
# WritingService Integration & Rejection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_writing_service_verify_citations():
    """Test WritingService.verify_citations method returns structured verification dict."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi.return_value = {"doi": "10.1000/1", "title": "Paper 1"}
    mock_llm = MagicMock()

    service = WritingService(mock_neo4j, mock_llm)
    result = await service.verify_citations(
        project_id="proj-1",
        draft_text="Discussing (10.1000/1).",
        assigned_dois=["10.1000/1"],
    )

    assert result["is_grounded"] is True
    assert result["passed"] is True
    assert result["verified_dois"] == ["10.1000/1"]
    assert result["hallucinated_dois"] == []


@pytest.mark.asyncio
async def test_writing_service_review_rejects_hallucinations(tmp_path):
    """Test review_section automatically sets approved=False and logs feedback when hallucination is detected."""
    mock_neo4j = AsyncMock()

    async def mock_get_paper(doi):
        if doi == "10.1000/valid":
            return {"doi": "10.1000/valid", "title": "Valid Paper"}
        return None

    mock_neo4j.get_paper_by_doi.side_effect = mock_get_paper

    mock_llm = AsyncMock()
    # LLM might claim approved=True, but deterministic verification must override it
    mock_llm.complete.return_value = CompletionResponse(
        text=json.dumps({
            "approved": True,
            "scores": {
                "citation_coverage": 5,
                "coherence": 5,
                "synthesis": 5,
                "academic_tone": 5,
                "completeness": 5,
            },
            "feedback": ["Great draft."],
            "missing_citations": [],
        }),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    service = WritingService(mock_neo4j, mock_llm, projects_dir=str(tmp_path))
    draft = "Grounded (10.1000/valid) but also hallucinated (10.1000/fake-paper)."

    review = await service.review_section(
        project_id="proj-1",
        section_title="Methods",
        draft_text=draft,
        paper_dois=["10.1000/valid"],
    )

    # Verification must force approved to False
    assert review["approved"] is False
    assert "10.1000/fake-paper" in review["hallucinated_citations"]
    assert any("Hallucinated citation(s) detected" in f for f in review["feedback"])
