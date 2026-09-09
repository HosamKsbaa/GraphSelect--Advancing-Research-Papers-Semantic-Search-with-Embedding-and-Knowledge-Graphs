"""Adversarial Stress Test Suite for Milestone M2 Continuous Library Ingestion (US1 / R1).

Adversarially challenges and empirically evaluates:
1. Dirty punctuation around DOIs (nested parentheses, unicode smart quotes, markdown, trailing punctuation, URLs with anchors).
2. Title matching boundary conditions (0.899 vs 0.900, SequenceMatcher token sort, unconfirmed title handling).
3. Relevance gate boundary conditions (cosine similarity at 0.7499 vs 0.7500, multi-RQ max, zero/mismatched vectors).
4. Preprints with 0 references & NoneType fragility (empty references, null references from OpenAlex, null authors).
5. Retraction alerts and auditability (is_retracted Neo4j parameter propagation, warning tag emission, board alerts).
"""
from __future__ import annotations

import asyncio
import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from core.errors.enhancement_errors import TitleConfirmationRequiredError, UnresolvableIdentifierError
from features.chat.service import ChatService
from features.ingestion.graph_wiring import (
    build_wiring_parameters,
    execute_bidirectional_wiring,
    get_bulk_ingest_cypher_query,
    wire_paper_bidirectional,
)
from features.ingestion.identifier_extractor import (
    clean_punctuation,
    compute_title_similarity,
    extract_all_identifiers,
    extract_arxiv_ids,
    extract_dois,
    extract_urls,
    match_title_candidate,
    normalize_identifier_input,
)
from features.ingestion.ingestion_service import IngestionService
from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    IdentifierType,
    IngestUserPaperInput,
    IngestionSource,
    TitleConfirmationChip,
    UserIngestedPaper,
)
from features.ingestion.relevance_gate import (
    compute_cosine_similarity,
    evaluate_paper_for_project,
    evaluate_paper_relevance,
    fetch_project_rq_embeddings,
)


# ==============================================================================
# 1. ADVERSARIAL DIRTY PUNCTUATION AROUND DOIS AND IDENTIFIERS
# ==============================================================================

@pytest.mark.parametrize(
    ("dirty_text", "expected_doi"),
    [
        ("((10.1038/nature12373)).", "10.1038/nature12373"),
        ("[[[10.1145/3292500]]],", "10.1145/3292500"),
        ("“10.1038/nature12373”", "10.1038/nature12373"),
        ("‘10.1038/nature12373’", "10.1038/nature12373"),
        ("“‘10.1016/j.cell.2021.01.001’”", "10.1016/j.cell.2021.01.001"),
        ("<10.1007/s00222-011-0315-4>", "10.1007/s00222-011-0315-4"),
        ("Did you read 10.1038/nature12373?", "10.1038/nature12373"),
        ("Check this: 10.1038/nature12373!", "10.1038/nature12373"),
        ("10.1038/nature12373;", "10.1038/nature12373"),
        ("10.1038/nature12373...", "10.1038/nature12373"),
        ("doi: 10.1038/nature12373", "10.1038/nature12373"),
        ("doi:  10.1038/nature12373", "10.1038/nature12373"),
        ("10.1038/NATURE12373", "10.1038/nature12373"),
        ("https://doi.org/10.1038/nature12373.", "10.1038/nature12373"),
        ("https://doi.org/10.1038/nature12373?utm_source=chat#sec-1", "10.1038/nature12373"),
    ],
)
def test_adversarial_extract_dois_dirty_punctuation(dirty_text: str, expected_doi: str) -> None:
    """Ensure extract_dois strips severe nested, unicode, markdown, and URL trailing punctuation."""
    extracted = extract_dois(dirty_text)
    assert len(extracted) == 1
    assert extracted[0] == expected_doi


def test_adversarial_extract_dois_in_markdown_links() -> None:
    """Extract canonical DOIs from complex markdown and parenthesized links."""
    text1 = "[Nature Paper](https://doi.org/10.1038/nature12373)"
    text2 = "([Deep Learning Reference](https://doi.org/10.1038/nature12373))"
    text3 = "[Local DOI](10.1145/3292500)"

    assert extract_dois(text1) == ["10.1038/nature12373"]
    assert extract_dois(text2) == ["10.1038/nature12373"]
    assert extract_dois(text3) == ["10.1145/3292500"]


def test_adversarial_extract_multiple_dois_in_parentheses() -> None:
    """Extract multiple comma- and semicolon-separated DOIs enclosed in parens."""
    text = "(see 10.1038/nature12373; also 10.1145/3292500, cf. 10.1016/j.cag.2025.04.012)"
    dois = extract_dois(text)
    assert len(dois) == 3
    assert dois == [
        "10.1038/nature12373",
        "10.1145/3292500",
        "10.1016/j.cag.2025.04.012",
    ]


@pytest.mark.parametrize(
    ("dirty_input", "expected_type", "expected_norm"),
    [
        ("((10.1038/nature12373)).", IdentifierType.DOI, "10.1038/nature12373"),
        ("[link](https://doi.org/10.1038/nature12373)", IdentifierType.DOI, "10.1038/nature12373"),
        ("“arXiv: 2301.12345v2”", IdentifierType.ARXIV, "2301.12345v2"),
        ("(https://arxiv.org/abs/2301.12345)", IdentifierType.ARXIV, "2301.12345"),
        ("https://arxiv.org/pdf/2301.12345.pdf", IdentifierType.ARXIV, "2301.12345"), ("https://example.com/paper.html", IdentifierType.URL, "https://example.com/paper.html"),
        ("   ", IdentifierType.TITLE, ""),
        ("(((...)))", IdentifierType.TITLE, ""),
    ],
)
def test_adversarial_normalize_identifier_input(
    dirty_input: str, expected_type: IdentifierType, expected_norm: str
) -> None:
    """Validate normalize_identifier_input on heavily punctuated and malformed inputs."""
    id_type, norm = normalize_identifier_input(dirty_input)
    assert id_type == expected_type
    assert norm == expected_norm


@pytest.mark.asyncio
async def test_adversarial_chat_scanner_with_dirty_doi() -> None:
    """Chat service message with double-parenthesized trailing punctuation extracts canonical DOI."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = []
    mock_neo4j.get_project_papers.return_value = []

    mock_ingestion = MagicMock()
    mock_ingestion.dispatch_background_ingestion = MagicMock()
    chat_svc = ChatService(neo4j_service=mock_neo4j, ingestion_service=mock_ingestion)

    await chat_svc.create_chat("proj-adv", "Adversarial Chat")
    chats = await chat_svc.list_chats("proj-adv")
    chat_id = chats[0].id

    await chat_svc.send_message(
        project_id="proj-adv",
        chat_id=chat_id,
        user_text="Have you seen ((10.1038/nature12373)).? It is crucial.",
    )

    mock_ingestion.dispatch_background_ingestion.assert_called_once()
    called_inp = mock_ingestion.dispatch_background_ingestion.call_args[0][0]
    assert called_inp.identifier == "10.1038/nature12373"


# ==============================================================================
# 2. TITLE MATCHING BOUNDARY TESTS (0.899 VS 0.900)
# ==============================================================================

@pytest.mark.asyncio
async def test_title_matching_boundary_at_0899_rejected() -> None:
    """Similarity of 0.8990 is strictly below 0.900 threshold and MUST return None."""
    mock_oa = AsyncMock()
    cand = MagicMock()
    cand.title = "Target Test Paper Title"
    mock_oa.search_by_title.return_value = [cand]

    with patch("features.ingestion.identifier_extractor.compute_title_similarity", return_value=0.8990):
        chip = await match_title_candidate("Target Test Paper Title", mock_oa, threshold=0.90)
        assert chip is None


@pytest.mark.asyncio
async def test_title_matching_boundary_at_08999_rejected() -> None:
    """Similarity of 0.8999 is strictly below 0.900 threshold and MUST return None."""
    mock_oa = AsyncMock()
    cand = MagicMock()
    cand.title = "Target Test Paper Title"
    mock_oa.search_by_title.return_value = [cand]

    with patch("features.ingestion.identifier_extractor.compute_title_similarity", return_value=0.8999):
        chip = await match_title_candidate("Target Test Paper Title", mock_oa, threshold=0.90)
        assert chip is None


@pytest.mark.asyncio
async def test_title_matching_boundary_at_09000_accepted() -> None:
    """Similarity of exactly 0.9000 satisfies >= 0.90 threshold and MUST generate chip."""
    mock_oa = AsyncMock()
    cand = MagicMock()
    cand.title = "Target Test Paper Title"
    cand.openalex_id = "W123456"
    cand.doi = "10.1145/3292500"
    mock_oa.search_by_title.return_value = [cand]

    with patch("features.ingestion.identifier_extractor.compute_title_similarity", return_value=0.9000):
        chip = await match_title_candidate("Target Test Paper Title", mock_oa, threshold=0.90)
        assert chip is not None
        assert chip.similarity_score == 0.9000
        assert chip.resolved_openalex_id == "W123456"
        assert chip.resolved_doi == "10.1145/3292500"
        assert chip.status == "pending"


@pytest.mark.asyncio
async def test_title_matching_boundary_at_09001_accepted() -> None:
    """Similarity of 0.9001 satisfies >= 0.90 threshold and MUST generate chip."""
    mock_oa = AsyncMock()
    cand = MagicMock()
    cand.title = "Target Test Paper Title"
    cand.openalex_id = "W123456"
    cand.doi = "10.1145/3292500"
    mock_oa.search_by_title.return_value = [cand]

    with patch("features.ingestion.identifier_extractor.compute_title_similarity", return_value=0.9001):
        chip = await match_title_candidate("Target Test Paper Title", mock_oa, threshold=0.90)
        assert chip is not None
        assert chip.similarity_score == 0.9001


def test_title_similarity_real_strings_mathematical_boundary() -> None:
    """Verify real string similarity calculation on exact mathematical boundary.

    Target: 'Deep Residual Learning for Image Recognition' (44 chars)
    Candidate 1 (-8 chars): 'Deep Residual Learning for Image Rec' (36 chars) -> 2*36/(36+44) = 0.9000.
    Candidate 2 (-9 chars): 'Deep Residual Learning for Image Re' (35 chars) -> 2*35/(35+44) = 0.8861.
    """
    target = "Deep Residual Learning for Image Recognition"
    cand_at_boundary = "Deep Residual Learning for Image Rec"
    cand_below_boundary = "Deep Residual Learning for Image Re"

    score_at_boundary = compute_title_similarity(cand_at_boundary, target)
    score_below_boundary = compute_title_similarity(cand_below_boundary, target)

    assert pytest.approx(score_at_boundary, 1e-4) == 0.9000
    assert score_below_boundary < 0.9000


@pytest.mark.asyncio
async def test_ingestion_service_unconfirmed_title_below_threshold_raises_error() -> None:
    """When title search returns best candidate < 0.90, TitleConfirmationRequiredError is raised."""
    mock_neo4j = AsyncMock()
    mock_oa = AsyncMock()
    cand = MagicMock()
    cand.title = "Completely Different Topic and Field"
    mock_oa.search_by_title.return_value = [cand]

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(
        identifier="Quantum Computing In Cryptography",
        project_id="proj-title",
        run_id="run-title",
        is_title_confirmed=False,
    )

    with pytest.raises(TitleConfirmationRequiredError):
        await service.ingest_paper(inp)


# ==============================================================================
# 3. RELEVANCE GATE BOUNDARY TESTS (0.7499 VS 0.7500)
# ==============================================================================

def test_relevance_gate_boundary_07499_blocks_expansion() -> None:
    """Cosine similarity of exactly 0.7499 is below 0.7500 and MUST block deep expansion."""
    cos_val = 0.7499
    sin_val = math.sqrt(1.0 - cos_val**2)
    paper_vec = [cos_val, sin_val]
    rq_vec = [1.0, 0.0]

    sim = compute_cosine_similarity(paper_vec, rq_vec)
    assert pytest.approx(sim, 1e-4) == 0.7499

    can_expand, score = evaluate_paper_relevance(paper_vec, [rq_vec], threshold=0.75)
    assert pytest.approx(score, 1e-4) == 0.7499
    assert can_expand is False


def test_relevance_gate_boundary_074999_blocks_expansion() -> None:
    """Cosine similarity of 0.74999 is below 0.7500 and MUST block deep expansion."""
    cos_val = 0.74999
    sin_val = math.sqrt(1.0 - cos_val**2)
    paper_vec = [cos_val, sin_val]
    rq_vec = [1.0, 0.0]

    can_expand, score = evaluate_paper_relevance(paper_vec, [rq_vec], threshold=0.75)
    assert can_expand is False


def test_relevance_gate_boundary_07500_allows_expansion() -> None:
    """Cosine similarity of exactly 0.7500 meets 0.7500 threshold and MUST allow expansion."""
    cos_val = 0.7500
    sin_val = math.sqrt(1.0 - cos_val**2)
    paper_vec = [cos_val, sin_val]
    rq_vec = [1.0, 0.0]

    sim = compute_cosine_similarity(paper_vec, rq_vec)
    assert pytest.approx(sim, 1e-4) == 0.7500

    can_expand, score = evaluate_paper_relevance(paper_vec, [rq_vec], threshold=0.75)
    assert pytest.approx(score, 1e-4) == 0.7500
    assert can_expand is True


def test_relevance_gate_boundary_07501_allows_expansion() -> None:
    """Cosine similarity of 0.7501 exceeds 0.7500 threshold and MUST allow expansion."""
    cos_val = 0.7501
    sin_val = math.sqrt(1.0 - cos_val**2)
    paper_vec = [cos_val, sin_val]
    rq_vec = [1.0, 0.0]

    can_expand, score = evaluate_paper_relevance(paper_vec, [rq_vec], threshold=0.75)
    assert can_expand is True


def test_relevance_gate_multi_rq_max_behavior() -> None:
    """Relevance gate takes maximum similarity across multiple active research questions."""
    paper_vec = [1.0, 0.0]
    # RQ1: similarity 0.30
    rq1 = [0.30, math.sqrt(1.0 - 0.30**2)]
    # RQ2: similarity 0.7499 (fails alone)
    rq2 = [0.7499, math.sqrt(1.0 - 0.7499**2)]
    # RQ3: similarity 0.7500 (passes)
    rq3 = [0.7500, math.sqrt(1.0 - 0.7500**2)]

    # Without RQ3: max is 0.7499 -> False
    can_expand_fail, score_fail = evaluate_paper_relevance(paper_vec, [rq1, rq2], threshold=0.75)
    assert can_expand_fail is False
    assert pytest.approx(score_fail, 1e-4) == 0.7499

    # With RQ3: max is 0.7500 -> True
    can_expand_pass, score_pass = evaluate_paper_relevance(paper_vec, [rq1, rq2, rq3], threshold=0.75)
    assert can_expand_pass is True
    assert pytest.approx(score_pass, 1e-4) == 0.7500


def test_relevance_gate_adversarial_vectors_zero_norm_and_dimension_mismatch() -> None:
    """Vectors with zero norm or mismatched dimensionality safely return 0.0 without crash."""
    assert compute_cosine_similarity([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert compute_cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert compute_cosine_similarity(None, [1.0, 0.0]) == 0.0
    assert compute_cosine_similarity([1.0, 0.0], None) == 0.0

    can_expand, score = evaluate_paper_relevance(None, [[1.0, 0.0]])
    assert can_expand is False
    assert score == 0.0

    can_expand2, score2 = evaluate_paper_relevance([1.0, 0.0], [])
    assert can_expand2 is False
    assert score2 == 0.0


def test_relevance_gate_user_override_bypasses_negative_similarity() -> None:
    """User override forces can_expand_deeply=True even if similarity is negative or zero."""
    paper_vec = [-1.0, 0.0]
    rq_vec = [1.0, 0.0]
    can_expand, score = evaluate_paper_relevance(paper_vec, [rq_vec], threshold=0.75, is_user_override=True)
    assert can_expand is True
    assert pytest.approx(score, 1e-4) == -1.0


# ==============================================================================
# 4. PREPRINTS WITH 0 REFERENCES & FRAGILITY CHALLENGES
# ==============================================================================

@pytest.mark.asyncio
async def test_clean_preprint_zero_references_success() -> None:
    """A fresh preprint with referenced_works=[] ingests cleanly with 0 citation links."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.48550/arxiv.2401.00001"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.48550/arxiv.2401.00001",
        "title": "Clean Preprint Zero References",
        "year": 2024,
        "abstract": "Preprint abstract",
        "openalex_id": "W99999",
        "referenced_works": [],
        "is_retracted": False,
        "authors": ["Author One"],
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(identifier="10.48550/arxiv.2401.00001", project_id="proj-pre", run_id="run-pre")
    out = await service.ingest_paper(inp)

    assert out.status == "success"
    assert out.doi == "10.48550/arxiv.2401.00001"
    assert out.citation_links_created == 0


@pytest.mark.asyncio
async def test_preprint_none_referenced_works_vulnerability() -> None:
    """REMEDIATED: When OpenAlex returns referenced_works=None (null in API).

    Verifies that null referenced_works coalesces to [] and ingests cleanly without TypeError.
    """
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.48550/arxiv.2401.00002"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.48550/arxiv.2401.00002",
        "title": "Preprint With None References",
        "year": 2024,
        "abstract": "Abstract",
        "openalex_id": "W99998",
        "referenced_works": None,  # OpenAlex returns null
        "is_retracted": False,
        "authors": ["Author One"],
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(identifier="10.48550/arxiv.2401.00002", project_id="proj-pre", run_id="run-pre")

    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.doi == "10.48550/arxiv.2401.00002"
    assert out.citation_links_created == 0


def test_paper_create_to_dict_authors_none_vulnerability() -> None:
    """REMEDIATED: When paper object has authors=None, _paper_create_to_dict coalesces to [].

    Verifies that 'getattr(paper, "authors", None) or []' prevents TypeError and returns empty list.
    """
    service = IngestionService(neo4j_service=None, openalex_service=None)
    mock_paper = MagicMock()
    mock_paper.doi = "10.1038/nature12373"
    mock_paper.title = "Sample Paper"
    mock_paper.authors = None  # Missing/unparsed author list

    res = service._paper_create_to_dict(mock_paper)
    assert res["authors"] == []


@pytest.mark.asyncio
async def test_preprint_none_authors_and_none_references_success() -> None:
    """REMEDIATED: When OpenAlex returns both authors=None and referenced_works=None.

    Verifies that both null fields coalesce to [] and ingest without Pydantic or iteration error.
    """
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.48550/arxiv.2401.00003"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.48550/arxiv.2401.00003",
        "title": "Preprint With None Authors and References",
        "year": 2024,
        "abstract": "Abstract",
        "openalex_id": "W99997",
        "referenced_works": None,
        "is_retracted": False,
        "authors": None,
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(identifier="10.48550/arxiv.2401.00003", project_id="proj-pre", run_id="run-pre")

    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.doi == "10.48550/arxiv.2401.00003"
    assert out.citation_links_created == 0


def test_user_ingested_paper_rejects_authors_none() -> None:
    """VULNERABILITY CHALLENGE: UserIngestedPaper raises ValidationError if authors=None."""
    with pytest.raises(ValidationError) as exc_info:
        UserIngestedPaper(
            raw_identifier="10.1038/nature12373",
            doi="10.1038/nature12373",
            title="Sample Paper",
            authors=None,  # type: ignore[arg-type]
        )
    assert "Input should be a valid list" in str(exc_info.value)


# ==============================================================================
# 5. RETRACTION ALERTS & AUDITABILITY CHALLENGES
# ==============================================================================

@pytest.mark.asyncio
async def test_retracted_paper_board_notification_contains_warning_tag() -> None:
    """Retracted paper ingestion issues board message with tag='warning' and retraction warning."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1016/j.retracted.001"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.1016/j.retracted.001",
        "title": "Fraudulent Vaccine Study",
        "year": 2021,
        "abstract": "Debunked claim.",
        "openalex_id": "W77777",
        "referenced_works": [],
        "is_retracted": True,
        "authors": ["Discredited Author"],
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(
        identifier="10.1016/j.retracted.001",
        project_id="proj-retract",
        run_id="run-retract",
    )
    out = await service.ingest_paper(inp)

    assert out.status == "success"
    assert out.doi == "10.1016/j.retracted.001"

    # Inspect Neo4j board notification call
    write_calls = mock_neo4j.execute_write.call_args_list
    # The board notification is the second execute_write call
    board_call = write_calls[1]
    params = board_call[0][1]
    assert params["tag"] == "warning"
    assert "⚠️ RETRACTION NOTICE: Paper is flagged as retracted." in params["content"]
    assert params["doi"] == "10.1016/j.retracted.001"


@pytest.mark.asyncio
async def test_non_retracted_paper_board_notification_uses_insight_tag() -> None:
    """Standard non-retracted paper uses tag='insight' and has no retraction alert."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1016/j.valid.001"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.1016/j.valid.001",
        "title": "Valid Study",
        "year": 2023,
        "abstract": "Valid study abstract.",
        "openalex_id": "W66666",
        "referenced_works": [],
        "is_retracted": False,
        "authors": ["Valid Author"],
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(
        identifier="10.1016/j.valid.001",
        project_id="proj-valid",
        run_id="run-valid",
    )
    out = await service.ingest_paper(inp)

    assert out.status == "success"

    write_calls = mock_neo4j.execute_write.call_args_list
    board_call = write_calls[1]
    params = board_call[0][1]
    assert params["tag"] == "insight"
    assert "RETRACTION NOTICE" not in params["content"]


def test_retraction_audit_fields_in_wiring_parameters() -> None:
    """Verify is_retracted, run_id, and created_in_stage are serialized for Cypher persistence."""
    paper = UserIngestedPaper(
        raw_identifier="10.1016/j.retracted.002",
        doi="10.1016/j.retracted.002",
        title="Retracted Publication",
        is_retracted=True,
    )
    params = build_wiring_parameters(
        paper=paper,
        project_id="proj-audit",
        run_id="run-audit-999",
        stage_index=3,
    )
    assert params["is_retracted"] is True
    assert params["run_id"] == "run-audit-999"
    assert params["created_in_stage"] == 3
    assert params["doi"] == "10.1016/j.retracted.002"
