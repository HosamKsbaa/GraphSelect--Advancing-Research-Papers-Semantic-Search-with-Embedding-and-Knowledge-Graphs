"""Tests for OpenAlex client, rate limiting, abstract reconstruction, and atomic retrieval."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter
from core.paper_retrieval.service import PaperRetrievalService
from features.retrieval.models import PaperCreate


# ==============================================================================
# SECTION 1: INVERTED INDEX ABSTRACT RECONSTRUCTION
# ==============================================================================

def test_reconstruct_abstract_basic() -> None:
    """Test standard ordered inverted index reconstruction."""
    inverted: dict[str, list[int]] = {"Hello": [0], "world": [1]}
    assert OpenAlexService._reconstruct_abstract(inverted) == "Hello world"
    assert OpenAlexService.reconstruct_abstract(inverted) == "Hello world"


def test_reconstruct_abstract_unordered() -> None:
    """Test reconstructing abstract when tokens appear out of order."""
    inverted: dict[str, list[int]] = {"world": [1], "Hello": [0]}
    assert OpenAlexService._reconstruct_abstract(inverted) == "Hello world"


def test_reconstruct_abstract_repeated_tokens() -> None:
    """Test reconstructing abstract with duplicate words at different positions."""
    inverted: dict[str, list[int]] = {
        "is": [1, 3],
        "this": [0],
        "a": [2],
        "test": [4],
    }
    assert OpenAlexService._reconstruct_abstract(inverted) == "this is a is test"


def test_reconstruct_abstract_edge_cases() -> None:
    """Test empty, None, and invalid inputs gracefully return None."""
    assert OpenAlexService._reconstruct_abstract(None) is None
    assert OpenAlexService._reconstruct_abstract({}) is None
    assert OpenAlexService._reconstruct_abstract("not a dict") is None  # type: ignore[arg-type]
    assert OpenAlexService._reconstruct_abstract({"empty_positions": []}) is None


# ==============================================================================
# SECTION 2: CLIENT AUTHENTICATION & HEADER CONFIGURATION
# ==============================================================================

def test_openalex_client_polite_pool_headers() -> None:
    """Test polite pool User-Agent is set when API key is empty or placeholder."""
    service_no_key = OpenAlexService(api_key="")
    assert "User-Agent" in service_no_key._client.headers
    assert "mailto:" in service_no_key._client.headers["User-Agent"]
    assert service_no_key._api_key == ""

    service_placeholder = OpenAlexService(api_key="your_openalex_api_key_here")
    assert service_placeholder._api_key == ""
    assert "mailto:" in service_placeholder._client.headers["User-Agent"]


def test_openalex_client_api_key_auth() -> None:
    """Test client stores API key when real key is provided."""
    service = OpenAlexService(api_key="real_key_12345")
    assert service._api_key == "real_key_12345"


# ==============================================================================
# SECTION 3: RATE LIMITING & AIMD BACKOFF
# ==============================================================================

@pytest.mark.asyncio
async def test_adaptive_rate_limiter_aimd() -> None:
    """Test AdaptiveRateLimiter token acquisition, 429 halving, and additive recovery."""
    limiter = AdaptiveRateLimiter(initial_rate=10.0, min_rate=1.0, recovery_increment=0.5)
    assert limiter.current_rate == 10.0

    # 429 Multiplicative Decrease: 10.0 -> 5.0
    new_rate = limiter.on_429()
    assert new_rate == 5.0
    assert limiter.current_rate == 5.0

    # Another 429: 5.0 -> 2.5
    limiter.on_429()
    assert limiter.current_rate == 2.5

    # On success: Additive increase 2.5 -> 3.0
    recovered = limiter.on_success()
    assert recovered == 3.0

    # Reset
    limiter.reset()
    assert limiter.current_rate == 10.0


@pytest.mark.asyncio
async def test_openalex_request_handles_429_retry() -> None:
    """Test OpenAlexService retries on HTTP 429 and updates rate limiter."""
    mock_limiter = MagicMock(spec=AdaptiveRateLimiter)
    mock_limiter.acquire = AsyncMock()

    service = OpenAlexService(api_key="test_key", rate_limiter=mock_limiter)

    resp_429 = httpx.Response(status_code=429, request=httpx.Request("GET", "https://api.openalex.org/test"))
    resp_200 = httpx.Response(
        status_code=200,
        json={"id": "W123", "title": "Test Work"},
        request=httpx.Request("GET", "https://api.openalex.org/test"),
    )

    with patch.object(service._client, "request", side_effect=[resp_429, resp_200]) as mock_req:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await service._request("GET", "/test")
            assert result["id"] == "W123"
            assert mock_req.call_count == 2
            mock_limiter.on_429.assert_called_once()
            mock_limiter.on_success.assert_called_once()
            mock_sleep.assert_called_once()


# ==============================================================================
# SECTION 4: WORK PARSING, CITATIONS & REFERENCES
# ==============================================================================

@pytest.mark.asyncio
async def test_get_paper_by_doi_success() -> None:
    """Test fetching and parsing a single paper by DOI."""
    service = OpenAlexService(api_key="test_key")

    mock_json = {
        "doi": "https://doi.org/10.1145/1234567.890",
        "title": "Graph Attention Networks for Scholarly Retrieval",
        "publication_year": 2024,
        "cited_by_count": 42,
        "id": "https://openalex.org/W99999",
        "publication_date": "2024-05-15",
        "abstract_inverted_index": {"Graph": [0], "attention": [1], "models.": [2]},
        "referenced_works": ["https://openalex.org/W111", "https://openalex.org/W222"],
    }

    with patch.object(service, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_json

        paper = await service.get_paper_by_doi("10.1145/1234567.890")

        assert isinstance(paper, PaperCreate)
        assert paper.doi == "10.1145/1234567.890"
        assert paper.title == "Graph Attention Networks for Scholarly Retrieval"
        assert paper.abstract == "Graph attention models."
        assert paper.year == 2024
        assert paper.cited_by_count == 42
        assert paper.openalex_id == "https://openalex.org/W99999"


@pytest.mark.asyncio
async def test_get_citations_and_references() -> None:
    """Test fetching incoming citations and outgoing references."""
    service = OpenAlexService(api_key="test_key")

    citations_response = {
        "results": [
            {"doi": "https://doi.org/10.1000/citing1"},
            {"doi": "https://doi.org/10.1000/citing2"},
        ]
    }
    references_response = {
        "results": [
            {"doi": "https://doi.org/10.1000/ref1"},
            {"doi": "https://doi.org/10.1000/ref2"},
        ]
    }

    with patch.object(service, "_request", side_effect=[citations_response, references_response]) as mock_req:
        citations = await service.get_citations("10.1000/seed", openalex_id="W12345")
        assert citations == ["10.1000/citing1", "10.1000/citing2"]

        references = await service.get_references("10.1000/seed", openalex_id="W12345")
        assert references == ["10.1000/ref1", "10.1000/ref2"]

        # Verify filter formatting
        assert mock_req.call_args_list[0][1]["params"]["filter"] == "cites:W12345"
        assert mock_req.call_args_list[1][1]["params"]["filter"] == "cited_by:W12345"


# ==============================================================================
# SECTION 5: ATOMIC PAPER RETRIEVAL PIPELINE
# ==============================================================================

@pytest.mark.asyncio
async def test_paper_retrieval_service_pipeline(tmp_path: object) -> None:
    """Test PaperRetrievalService atomic execution: fetch, store, author/venue linking, references, embedding, backup."""
    mock_neo4j = AsyncMock()
    mock_neo4j.paper_exists.return_value = False
    mock_neo4j.create_paper.return_value = {"doi": "10.1000/p1"}
    mock_neo4j.execute_write.return_value = []
    mock_neo4j.ensure_stub_and_cite.return_value = None
    mock_neo4j.store_paper_embedding.return_value = None
    mock_neo4j.add_paper_to_project.return_value = None

    mock_openalex = AsyncMock()
    paper_create = PaperCreate(
        doi="10.1000/p1",
        title="Knowledge Graph Discovery",
        abstract="Knowledge graphs enhance semantic discovery.",
        year=2025,
        cited_by_count=10,
        openalex_id="W8888",
    )
    mock_openalex.get_paper_by_doi.return_value = paper_create
    mock_openalex.get_references.return_value = ["10.1000/ref_a", "10.1000/ref_b"]
    mock_openalex.get_citations.return_value = ["10.1000/cite_x"]

    # OpenAlex detailed work payload for authors and venue
    mock_openalex._request.return_value = {
        "authorships": [
            {
                "author": {"display_name": "Dr. Graph", "id": "https://openalex.org/A111"},
                "institutions": [{"display_name": "AI Institute"}],
            }
        ],
        "primary_location": {
            "source": {"display_name": "Journal of Graph Learning", "id": "https://openalex.org/V222"}
        },
        "referenced_works": [],
    }

    mock_embedding_provider = AsyncMock()
    mock_embedding_provider.model_name = "gemini-embedding-2"
    mock_embedding_provider.embed_document.return_value = [0.1] * 768

    retrieval_service = PaperRetrievalService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        embedding_provider=mock_embedding_provider,
        projects_dir=str(tmp_path),
    )

    full_paper = await retrieval_service.retrieve_paper("10.1000/p1", project_id="proj-test-123")

    # Assertions on metadata & embedding
    assert full_paper.metadata.doi == "10.1000/p1"
    assert full_paper.metadata.title == "Knowledge Graph Discovery"
    assert full_paper.metadata.authors == ["Dr. Graph"]
    assert full_paper.metadata.venue == "Journal of Graph Learning"
    assert full_paper.metadata.references == ["10.1000/ref_a", "10.1000/ref_b"]
    assert full_paper.metadata.citations == ["10.1000/cite_x"]
    assert full_paper.embedding == [0.1] * 768
    assert full_paper.already_existed is False

    # Verify OpenAlex get_references was called
    mock_openalex.get_references.assert_called_once_with("10.1000/p1", max_results=20, openalex_id="W8888")

    # Verify reference and citation stub creations
    assert mock_neo4j.ensure_stub_and_cite.call_count == 3
    # 2 outgoing references (doi -> ref_doi)
    mock_neo4j.ensure_stub_and_cite.assert_any_call("10.1000/p1", "10.1000/ref_a")
    mock_neo4j.ensure_stub_and_cite.assert_any_call("10.1000/p1", "10.1000/ref_b")
    # 1 incoming citation (cite_doi -> doi)
    mock_neo4j.ensure_stub_and_cite.assert_any_call("10.1000/cite_x", "10.1000/p1")

    # Verify embedding was called with title
    mock_embedding_provider.embed_document.assert_called_once_with(
        text="Knowledge graphs enhance semantic discovery.",
        title="Knowledge Graph Discovery",
    )

    # Verify project linking
    mock_neo4j.add_paper_to_project.assert_called_once_with("proj-test-123", "10.1000/p1")
