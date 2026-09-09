"""Comprehensive test suite for Continuous Library Ingestion & Bidirectional Wiring (US1 / R1).

Verifies:
- Regex identifier extraction & surrounding punctuation stripping.
- Fuzzy title matching with >= 0.90 threshold for confirmation chips and < 0.90 rejection.
- Parameterized atomic Cypher bidirectional wiring query generation and mock execution.
- Relevance gate exact boundary testing (cos = 0.749 -> False, cos = 0.750 -> True, user override).
- Retraction auditing and public board notification emission.
- Fresh preprint empty references fallback.
- FastAPI REST endpoints: POST /api/ingestion/ingest-paper, POST /api/ingestion/confirm-title.
- Crawler recursive expansion guard (can_expand_deeply == False aborts expansion).
- Retrieval deep content extraction guard (can_expand_deeply == False raises HTTP 403).
- Chat service conversational scanner hook.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.errors.enhancement_errors import EnhancementToolError, TitleConfirmationRequiredError, UnresolvableIdentifierError
from features.chat.models import ChatMessage
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
    UserIngestedPaper,
)
from features.ingestion.relevance_gate import (
    compute_cosine_similarity,
    evaluate_paper_relevance,
)
from features.retrieval.service import RetrievalService
from features.search.crawler_service import CrawlerService
from main import app


# ==============================================================================
# 1. Identifier Extraction & Punctuation Cleaning Tests
# ==============================================================================

def test_clean_punctuation() -> None:
    """Ensure trailing and leading punctuation are cleanly stripped."""
    assert clean_punctuation("(10.1145/3292500).") == "10.1145/3292500"
    assert clean_punctuation("[10.1038/nature12373]") == "10.1038/nature12373"
    assert clean_punctuation("<10.1007/s00222-011-0315-4>;") == "10.1007/s00222-011-0315-4"
    assert clean_punctuation('"10.1016/j.cag.2025.04.012",') == "10.1016/j.cag.2025.04.012"


def test_extract_dois() -> None:
    """Extract and normalize canonical lowercase DOIs from messy chat text."""
    text = (
        "Check out this seminal paper (see 10.1145/3292500). "
        "Also relevant is [10.1038/Nature12373] and duplicate 10.1145/3292500."
    )
    dois = extract_dois(text)
    assert dois == ["10.1145/3292500", "10.1038/nature12373"]


def test_extract_arxiv_ids() -> None:
    """Extract normalized arXiv IDs from conversational text."""
    text = "We should inspect arXiv:2301.12345v2 and also 2106.09685 for LoRA."
    arxiv_ids = extract_arxiv_ids(text)
    assert arxiv_ids == ["2301.12345v2", "2106.09685"]


def test_extract_urls() -> None:
    """Extract standard URLs from text."""
    text = "Find details at https://example.com/paper.pdf and (http://openalex.org/W123)."
    urls = extract_urls(text)
    assert "https://example.com/paper.pdf" in urls
    assert "http://openalex.org/W123" in urls


def test_normalize_identifier_input_doi_url() -> None:
    """Recognize DOI URLs and convert to canonical DOI."""
    id_type, norm = normalize_identifier_input("https://doi.org/10.1145/3292500")
    assert id_type == IdentifierType.DOI
    assert norm == "10.1145/3292500"


def test_normalize_identifier_input_arxiv_url() -> None:
    """Recognize arXiv URLs and extract identifier."""
    id_type, norm = normalize_identifier_input("https://arxiv.org/abs/2301.12345")
    assert id_type == IdentifierType.ARXIV
    assert norm == "2301.12345"


def test_normalize_identifier_input_title() -> None:
    """Recognize free text as title identifier."""
    id_type, norm = normalize_identifier_input("Attention Is All You Need")
    assert id_type == IdentifierType.TITLE
    assert norm == "Attention Is All You Need"


def test_extract_all_identifiers() -> None:
    """Extract all distinct identifiers from a rich paragraph."""
    text = "Read 10.1145/3292500, arxiv:2401.00001, and https://arxiv.org/abs/2401.00001."
    extracted = extract_all_identifiers(text)
    dois = [val for t, val in extracted if t == IdentifierType.DOI]
    arxivs = [val for t, val in extracted if t == IdentifierType.ARXIV]
    assert "10.1145/3292500" in dois
    assert "2401.00001" in arxivs


# ==============================================================================
# 2. Fuzzy Title Matching Tests
# ==============================================================================

def test_compute_title_similarity_exact() -> None:
    """Exact title matches score 1.0."""
    score = compute_title_similarity(
        "Attention Is All You Need",
        "Attention is all you need"
    )
    assert score == 1.0


def test_compute_title_similarity_token_order() -> None:
    """Slight word reordering retains high token sort similarity."""
    score = compute_title_similarity(
        "Graph Neural Networks: A Comprehensive Survey",
        "A Comprehensive Survey on Graph Neural Networks"
    )
    assert score >= 0.85


@pytest.mark.asyncio
async def test_match_title_candidate_chip_generated() -> None:
    """Similarity >= 0.90 produces a TitleConfirmationChip."""
    mock_oa = AsyncMock()
    mock_candidate = MagicMock()
    mock_candidate.title = "Attention Is All You Need"
    mock_candidate.openalex_id = "W2741809807"
    mock_candidate.doi = "10.5555/3295222.3295349"
    mock_oa.search_by_title.return_value = [mock_candidate]

    chip = await match_title_candidate("Attention Is All You Need", mock_oa, threshold=0.90)
    assert chip is not None
    assert chip.similarity_score >= 0.90
    assert chip.resolved_openalex_id == "W2741809807"
    assert chip.resolved_doi == "10.5555/3295222.3295349"
    assert chip.status == "pending"


@pytest.mark.asyncio
async def test_match_title_candidate_rejected_below_threshold() -> None:
    """Similarity < 0.90 returns None without graph mutations."""
    mock_oa = AsyncMock()
    mock_candidate = MagicMock()
    mock_candidate.title = "Transformers for Image Classification at Scale"
    mock_candidate.openalex_id = "W3105742792"
    mock_candidate.doi = "10.48550/arxiv.2010.11929"
    mock_oa.search_by_title.return_value = [mock_candidate]

    chip = await match_title_candidate("Attention Is All You Need", mock_oa, threshold=0.90)
    assert chip is None


# ==============================================================================
# 3. Parameterized Cypher Bidirectional Wiring Tests
# ==============================================================================

def test_get_bulk_ingest_cypher_query() -> None:
    """Verify Cypher query contains FOREACH bidirectional clauses and parameters."""
    query = get_bulk_ingest_cypher_query()
    assert "MERGE (new_paper:Paper {doi: $doi})" in query
    assert "FOREACH (ref_doi IN $referenced_dois" in query
    assert "FOREACH (citing_doi IN $citing_library_dois" in query
    assert "new_paper.run_id = $run_id" in query
    assert "new_paper.created_in_stage = $created_in_stage" in query
    assert "new_paper.can_expand_deeply = $can_expand_deeply" in query
    assert "new_paper.is_retracted = $is_retracted" in query


def test_build_wiring_parameters() -> None:
    """Construct complete parameter dictionary from UserIngestedPaper."""
    paper = UserIngestedPaper(
        raw_identifier="10.1145/3292500",
        doi="10.1145/3292500",
        openalex_id="W12345",
        title="Sample Test Paper",
        year=2024,
        abstract="Test abstract",
        embedding=[0.1] * 768,
        referenced_dois=["10.1145/1111111", "10.1145/2222222"],
        can_expand_deeply=True,
        is_retracted=False,
    )
    params = build_wiring_parameters(
        paper=paper,
        project_id="proj-123",
        run_id="run-456",
        stage_index=2,
        citing_library_dois=["10.1145/9999999"],
    )
    assert params["doi"] == "10.1145/3292500"
    assert params["project_id"] == "proj-123"
    assert params["run_id"] == "run-456"
    assert params["can_expand_deeply"] is True
    assert params["is_retracted"] is False
    assert len(params["referenced_dois"]) == 2
    assert len(params["citing_library_dois"]) == 1


@pytest.mark.asyncio
async def test_wire_paper_bidirectional_mock() -> None:
    """Mock Cypher execution and verify link count calculation."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1145/3292500"}]
    paper = UserIngestedPaper(
        raw_identifier="10.1145/3292500",
        doi="10.1145/3292500",
        title="Sample Paper",
        referenced_dois=["10.1145/ref1", "10.1145/ref2"],
    )
    count = await wire_paper_bidirectional(
        neo4j_service=mock_neo4j,
        paper=paper,
        project_id="proj-1",
        run_id="run-1",
        citing_library_dois=["10.1145/cite1"],
    )
    assert count == 3
    mock_neo4j.execute_write.assert_called_once()


# ==============================================================================
# 4. Relevance Gate Boundary Condition Tests (FR-016)
# ==============================================================================

def test_compute_cosine_similarity_orthogonal() -> None:
    """Orthogonal vectors return 0.0."""
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    assert compute_cosine_similarity(vec_a, vec_b) == 0.0


def test_compute_cosine_similarity_identical() -> None:
    """Identical vectors return 1.0."""
    vec_a = [0.5, 0.5, 0.5]
    vec_b = [0.5, 0.5, 0.5]
    assert pytest.approx(compute_cosine_similarity(vec_a, vec_b), 1e-5) == 1.0


def test_relevance_gate_threshold_boundary_false() -> None:
    """Cosine similarity of exactly 0.749 evaluates to False."""
    paper_emb = [0.749, (1 - 0.749**2)**0.5]
    rq_emb = [1.0, 0.0]
    can_expand, score = evaluate_paper_relevance(paper_emb, [rq_emb], threshold=0.75)
    assert pytest.approx(score, 1e-3) == 0.749
    assert can_expand is False


def test_relevance_gate_threshold_boundary_true() -> None:
    """Cosine similarity of exactly 0.750 evaluates to True."""
    paper_emb = [0.750, (1 - 0.750**2)**0.5]
    rq_emb = [1.0, 0.0]
    can_expand, score = evaluate_paper_relevance(paper_emb, [rq_emb], threshold=0.75)
    assert pytest.approx(score, 1e-3) == 0.750
    assert can_expand is True


def test_relevance_gate_user_override() -> None:
    """Explicit user override flag sets can_expand_deeply = True regardless of similarity."""
    paper_emb = [0.2, (1 - 0.2**2)**0.5]
    rq_emb = [1.0, 0.0]
    can_expand, score = evaluate_paper_relevance(
        paper_emb, [rq_emb], threshold=0.75, is_user_override=True
    )
    assert can_expand is True


# ==============================================================================
# 5. Ingestion Service End-to-End Workflow Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_ingest_deterministic_doi_success() -> None:
    """Ingesting a canonical DOI resolves metadata, evaluates gate, and writes to Neo4j."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1145/3292500"}]
    # Return active RQ embedding that passes threshold (1.0)
    mock_neo4j.execute_read.return_value = [{"embedding": [1.0] + [0.0] * 767}]

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.1145/3292500",
        "title": "KDD Sample Paper",
        "year": 2019,
        "abstract": "Deep learning paper abstract.",
        "openalex_id": "W12345",
        "referenced_works": ["https://doi.org/10.1145/ref1"],
        "is_retracted": False,
    }]
    mock_oa.get_citations.return_value = []

    mock_llm = AsyncMock()
    mock_llm.embed_document.return_value = [1.0] + [0.0] * 767

    service = IngestionService(
        neo4j_service=mock_neo4j,
        openalex_service=mock_oa,
        embedding_service=mock_llm,
    )
    inp = IngestUserPaperInput(
        identifier="10.1145/3292500",
        project_id="proj-test",
        run_id="run-test",
    )
    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.doi == "10.1145/3292500"
    assert out.can_expand_deeply is True
    assert out.citation_links_created >= 1


@pytest.mark.asyncio
async def test_ingest_retracted_paper_flags_and_notifies() -> None:
    """Retracted paper sets is_retracted = True and posts warning to board."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1016/j.retracted.2023"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.1016/j.retracted.2023",
        "title": "Retracted Study",
        "year": 2023,
        "abstract": "Abstract",
        "openalex_id": "W99999",
        "referenced_works": [],
        "is_retracted": True,
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(
        neo4j_service=mock_neo4j,
        openalex_service=mock_oa,
    )
    inp = IngestUserPaperInput(
        identifier="10.1016/j.retracted.2023",
        project_id="proj-test",
        run_id="run-test",
    )
    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.doi == "10.1016/j.retracted.2023"
    # Verify notification wrote 'warning' tag
    write_calls = mock_neo4j.execute_write.call_args_list
    warning_emitted = any("warning" in str(call) for call in write_calls)
    assert warning_emitted is True


@pytest.mark.asyncio
async def test_ingest_arxiv_preprint_empty_references() -> None:
    """Fresh arXiv preprint with empty referenced_works ingests cleanly."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.48550/arxiv.2401.99999"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.search_by_title.return_value = [
        MagicMock(doi="10.48550/arxiv.2401.99999", openalex_id="W88888")
    ]
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.48550/arxiv.2401.99999",
        "title": "Fresh Preprint",
        "year": 2024,
        "abstract": "Preprint abstract",
        "openalex_id": "W88888",
        "referenced_works": [],
        "is_retracted": False,
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(
        neo4j_service=mock_neo4j,
        openalex_service=mock_oa,
    )
    inp = IngestUserPaperInput(
        identifier="2401.99999",
        project_id="proj-test",
        run_id="run-test",
    )
    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.citation_links_created == 0


@pytest.mark.asyncio
async def test_ingest_arxiv_preprint_null_references_and_authors() -> None:
    """Preprint with referenced_works=None and authors=None coalesces cleanly."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.48550/arxiv.2401.88888"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.48550/arxiv.2401.88888",
        "title": "Null Fields Preprint",
        "year": 2024,
        "abstract": "Abstract",
        "openalex_id": "W77777",
        "referenced_works": None,
        "is_retracted": False,
        "authors": None,
    }]
    mock_oa.get_citations.return_value = []

    service = IngestionService(neo4j_service=mock_neo4j, openalex_service=mock_oa)
    inp = IngestUserPaperInput(identifier="10.48550/arxiv.2401.88888", project_id="proj-null", run_id="run-null")
    out = await service.ingest_paper(inp)
    assert out.status == "success"
    assert out.citation_links_created == 0


@pytest.mark.asyncio
async def test_confirm_title_lifecycle() -> None:
    """Confirmation chip lifecycle (dismissed vs confirmed)."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_write.return_value = [{"doi": "10.1145/3292500"}]
    mock_neo4j.execute_read.return_value = []

    mock_oa = AsyncMock()
    mock_oa.batch_get_rich_papers.return_value = [{
        "doi": "10.1145/3292500",
        "title": "Confirmed Paper",
        "year": 2020,
        "abstract": "Abstract",
        "openalex_id": "W12345",
        "referenced_works": [],
        "is_retracted": False,
    }]

    service = IngestionService(
        neo4j_service=mock_neo4j,
        openalex_service=mock_oa,
    )

    # 1. Dismiss action
    dismiss_inp = ConfirmTitleIngestionInput(
        chip_id="chip-1",
        project_id="proj-1",
        confirmed=False,
        resolved_openalex_id="W12345",
        resolved_doi="10.1145/3292500",
        resolved_title="Confirmed Paper",
        run_id="run-1",
    )
    dismiss_out = await service.confirm_title_chip(dismiss_inp)
    assert dismiss_out.status == "dismissed"
    assert mock_neo4j.execute_write.call_count == 0

    # 2. Confirm action
    confirm_inp = ConfirmTitleIngestionInput(
        chip_id="chip-1",
        project_id="proj-1",
        confirmed=True,
        resolved_openalex_id="W12345",
        resolved_doi="10.1145/3292500",
        resolved_title="Confirmed Paper",
        run_id="run-1",
    )
    confirm_out = await service.confirm_title_chip(confirm_inp)
    assert confirm_out.status == "confirmed"
    assert confirm_out.doi == "10.1145/3292500"


# ==============================================================================
# 6. Crawler & Retrieval Guard Enforcement Tests (FR-016)
# ==============================================================================

@pytest.mark.asyncio
async def test_crawler_recursive_expansion_guard_aborts() -> None:
    """Crawler aborts 1-hop expansion if paper has can_expand_deeply=False."""
    mock_neo4j = AsyncMock()
    # Graph reports paper has can_expand_deeply=False
    mock_neo4j.execute_read.return_value = [{"can_expand": False}]

    mock_oa = AsyncMock()
    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_oa)

    res = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi="10.1145/surface_paper",
    )
    assert res.total_discovered == 0
    assert "can_expand_deeply is False" in res.traversal_summary[0]
    # No OpenAlex network requests should have been made
    mock_oa.get_citations.assert_not_called()


@pytest.mark.asyncio
async def test_retrieval_deep_content_extraction_guard() -> None:
    """RetrievalService blocks deep extraction if can_expand_deeply=False and no override."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"can_expand": False}]
    mock_oa = AsyncMock()

    retrieval = RetrievalService(neo4j=mock_neo4j, openalex=mock_oa)

    # Should raise EnhancementToolError (HTTP 403)
    with pytest.raises(EnhancementToolError) as exc_info:
        await retrieval.extract_deep_content("10.1145/surface_paper", user_override=False)
    assert exc_info.value.http_status_code == 403

    # With user_override=True, it succeeds
    allowed = await retrieval.extract_deep_content("10.1145/surface_paper", user_override=True)
    assert allowed["status"] == "extracted"


# ==============================================================================
# 7. Chat Service Conversational Scanner Hook Test
# ==============================================================================

@pytest.mark.asyncio
async def test_chat_service_scans_and_triggers_ingestion() -> None:
    """Chat message containing a DOI triggers continuous auto-ingestion."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = []
    mock_neo4j.get_project_papers.return_value = []

    mock_ingestion = MagicMock()
    mock_ingestion.dispatch_background_ingestion = MagicMock()
    chat_svc = ChatService(
        neo4j_service=mock_neo4j,
        ingestion_service=mock_ingestion,
    )

    # In-memory session setup
    await chat_svc.create_chat("proj-chat", "Test Chat")
    chats = await chat_svc.list_chats("proj-chat")
    chat_id = chats[0].id

    res = await chat_svc.send_message(
        project_id="proj-chat",
        chat_id=chat_id,
        user_text="Please analyze this paper: 10.1145/3292500 for our review.",
    )
    assert res is not None
    user_msg, asst_msg = res
    # Check that ingestion was triggered
    mock_ingestion.dispatch_background_ingestion.assert_called_once()
    called_inp = mock_ingestion.dispatch_background_ingestion.call_args[0][0]
    assert called_inp.identifier == "10.1145/3292500"
    # Check tool trace in assistant message
    trace_names = [t.tool_name for t in asst_msg.tool_traces]
    assert "ContinuousIngestion" in trace_names


# ==============================================================================
# 8. FastAPI API Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_ingest_paper_endpoint() -> None:
    """FastAPI endpoint POST /api/ingestion/ingest-paper returns valid contract."""
    from features.ingestion.router import get_ingestion_service
    mock_service = AsyncMock()
    mock_service.ingest_paper.return_value = {
        "status": "success",
        "doi": "10.1145/3292500",
        "openalex_id": "W12345",
        "title": "API Sample Paper",
        "citation_links_created": 5,
        "can_expand_deeply": True,
        "max_rq_relevance": 0.88,
        "message": "Ingested successfully",
    }

    app.dependency_overrides[get_ingestion_service] = lambda: mock_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/ingestion/ingest-paper",
                json={
                    "identifier": "10.1145/3292500",
                    "project_id": "proj-api",
                    "run_id": "run-api",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["doi"] == "10.1145/3292500"
            assert data["can_expand_deeply"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_confirm_title_endpoint() -> None:
    """FastAPI endpoint POST /api/ingestion/confirm-title returns valid contract."""
    from features.ingestion.router import get_ingestion_service
    mock_service = AsyncMock()
    mock_service.confirm_title_chip.return_value = {
        "status": "confirmed",
        "doi": "10.1145/3292500",
        "openalex_id": "W12345",
        "title": "API Sample Paper",
        "citation_links_created": 5,
        "can_expand_deeply": True,
    }

    app.dependency_overrides[get_ingestion_service] = lambda: mock_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/ingestion/confirm-title",
                json={
                    "chip_id": "chip-api-1",
                    "project_id": "proj-api",
                    "confirmed": True,
                    "resolved_openalex_id": "W12345",
                    "resolved_doi": "10.1145/3292500",
                    "resolved_title": "API Sample Paper",
                    "run_id": "run-api",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "confirmed"
            assert data["doi"] == "10.1145/3292500"
    finally:
        app.dependency_overrides.clear()

