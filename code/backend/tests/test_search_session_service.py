"""Unit tests for SearchSessionService backed by Neo4j."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from features.retrieval.models import PaperRead
from features.search.session_service import SearchSessionService
from features.sessions.models import SearchMode, SearchRequest, SessionStatus


@pytest.fixture
def mock_neo4j():
    svc = AsyncMock()
    svc.execute_write = AsyncMock(return_value=[])
    svc.execute_read = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def mock_openalex():
    svc = AsyncMock()
    svc.get_paper_by_doi = AsyncMock(
        return_value=PaperRead(
            doi="10.1145/3292500.3330919",
            title="Test Seed Paper",
            abstract="Seed abstract text",
            year=2020,
            cited_by_count=100,
            openalex_id="W123",
            publication_date="2020-01-01",
            source="openalex",
            authors=[],
            venue=None,
            keywords=[],
        )
    )
    return svc


@pytest.mark.asyncio
async def test_create_session_success(mock_neo4j, mock_openalex):
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    req = SearchRequest(
        seed_doi="10.1145/3292500.3330919",
        research_questions=["What is GNN?"],
        similarity_threshold=0.6,
        max_depth=2,
        mode=SearchMode.INTERACTIVE,
    )

    resp = await svc.create_session(req)
    assert resp.seed_paper_doi == "10.1145/3292500.3330919"
    assert resp.status == SessionStatus.CREATED
    assert mock_neo4j.execute_write.call_count >= 2


@pytest.mark.asyncio
async def test_create_session_missing_doi(mock_neo4j, mock_openalex):
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    req = MagicMock(spec=SearchRequest)
    req.seed_doi = None
    with pytest.raises(ValueError, match="seed_doi is required"):
        await svc.create_session(req)


@pytest.mark.asyncio
async def test_enqueue_papers_success(mock_neo4j, mock_openalex):
    mock_neo4j.execute_write.return_value = [{"c": {"campaign_id": "sess-1"}}]
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    res = await svc.enqueue_papers("sess-1", ["10.1000/1", "10.1000/2"])
    assert res["enqueued"] == 2
    assert res["dois"] == ["10.1000/1", "10.1000/2"]


@pytest.mark.asyncio
async def test_enqueue_papers_not_found(mock_neo4j, mock_openalex):
    mock_neo4j.execute_write.return_value = []
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    with pytest.raises(LookupError, match="Session not found"):
        await svc.enqueue_papers("nonexistent", ["10.1000/1"])


@pytest.mark.asyncio
async def test_get_session_found(mock_neo4j, mock_openalex):
    mock_neo4j.execute_read.return_value = [
        {"c": {"campaign_id": "sess-1", "seed_doi": "10.1000/1"}}
    ]
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    session_data = await svc.get_session("sess-1")
    assert session_data is not None
    assert session_data["campaign_id"] == "sess-1"


@pytest.mark.asyncio
async def test_get_session_not_found(mock_neo4j, mock_openalex):
    mock_neo4j.execute_read.return_value = []
    svc = SearchSessionService(neo4j=mock_neo4j, openalex=mock_openalex)
    session_data = await svc.get_session("nonexistent")
    assert session_data is None
