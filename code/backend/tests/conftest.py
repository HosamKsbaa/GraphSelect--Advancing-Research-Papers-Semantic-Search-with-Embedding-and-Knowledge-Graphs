"""Shared test fixtures for ALRS v2 backend tests."""
from __future__ import annotations

import os

os.environ.setdefault("OPENALEX_API_KEY", "test-openalex-key")
os.environ.setdefault("OPENALEX_MAILTO", "researcher@university.edu")
os.environ.setdefault("NEO4J_PASSWORD", "test-neo4j-password")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("SQLITE_TELEMETRY_PATH", "data/telemetry.sqlite")

from datetime import datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from features.retrieval.models import AuthorCreate, PaperCreate, PaperRead, VenueCreate
from features.sessions.models import SearchMode, SearchRequest, SessionStatus


# --- Sample Data Fixtures ---


@pytest.fixture
def sample_doi() -> str:
    """A known test DOI."""
    return "10.1145/3292500.3330919"


@pytest.fixture
def sample_paper_create(sample_doi: str) -> PaperCreate:
    """A sample PaperCreate model."""
    return PaperCreate(
        doi=sample_doi,
        title="Graph Neural Networks: A Review of Methods and Applications",
        abstract="Graph neural networks have been widely applied...",
        year=2019,
        cited_by_count=5000,
        openalex_id="W123456789",
        publication_date="2019-08-04",
        source="openalex",
    )


@pytest.fixture
def sample_paper_read(sample_doi: str) -> PaperRead:
    """A sample PaperRead model (no embedding)."""
    return PaperRead(
        doi=sample_doi,
        title="Graph Neural Networks: A Review of Methods and Applications",
        abstract="Graph neural networks have been widely applied...",
        year=2019,
        cited_by_count=5000,
        openalex_id="W123456789",
        publication_date="2019-08-04",
        source="openalex",
        authors=[],
        venue=None,
        keywords=[],
    )


@pytest.fixture
def sample_search_request() -> SearchRequest:
    """A sample search request."""
    return SearchRequest(
        seed_doi="10.1145/3292500.3330919",
        research_questions=[
            "How are GNNs applied to citation networks?",
            "What are the limitations of current GNN architectures?",
        ],
        similarity_threshold=0.5,
        max_depth=2,
        mode=SearchMode.INTERACTIVE,
    )


@pytest.fixture
def sample_embedding() -> list[float]:
    """A 768-dimensional embedding vector for testing."""
    import math

    # Create a normalized vector
    raw = [float(i) / 768.0 for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


# --- Deterministic Offline API Mock Fixtures (Constitution A59) ---


@pytest.fixture
def mock_openalex() -> AsyncMock:
    """Deterministic offline mock for OpenAlex polite pool client."""
    client = AsyncMock()
    client.get_work_by_doi = AsyncMock(
        return_value={
            "id": "https://openalex.org/W123456789",
            "doi": "https://doi.org/10.1145/3292500.3330919",
            "title": "Graph Neural Networks: A Review of Methods and Applications",
            "publication_year": 2019,
            "cited_by_count": 5000,
            "referenced_works": ["https://openalex.org/W987654321"],
            "abstract_inverted_index": {
                "Graph": [0],
                "neural": [1],
                "networks": [2],
                "review": [3],
            },
        }
    )
    client.search_works = AsyncMock(return_value=[])
    client.get_references = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_gemini_embedding(sample_embedding: list[float]) -> AsyncMock:
    """Deterministic offline mock for Gemini 768-dim embeddings."""
    svc = AsyncMock()
    svc.generate_embedding = AsyncMock(return_value=sample_embedding)
    svc.embed_text = AsyncMock(return_value=sample_embedding)
    return svc


@pytest.fixture
def mock_gemini_flash() -> AsyncMock:
    """Deterministic offline mock for Gemini 2.5 Flash responses."""
    svc = AsyncMock()
    response_mock = MagicMock()
    response_mock.text = "Deterministic mocked synthesis response."
    svc.generate_content = AsyncMock(return_value=response_mock)
    return svc


# --- Mock Service Fixtures ---


@pytest.fixture
def mock_neo4j_service() -> AsyncMock:
    """Mock Neo4j service with common method stubs."""
    service = AsyncMock()
    service.connect = AsyncMock()
    service.close = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    service.execute_read = AsyncMock(return_value=[])
    service.execute_write = AsyncMock(return_value=[])
    service.execute_query = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_mysql_service() -> AsyncMock:
    """Legacy stub for test migration only."""
    service = AsyncMock()
    service.connect = AsyncMock()
    service.close = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    service.execute = AsyncMock(return_value=1)
    service.fetch_one = AsyncMock(return_value=None)
    service.fetch_all = AsyncMock(return_value=[])
    service.initialize_schema = AsyncMock()
    return service


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings with all required fields."""
    settings = MagicMock()
    settings.gemini_api_key = "test-gemini-key"
    settings.openalex_api_key = "test-openalex-key"
    settings.openalex_mailto = "researcher@university.edu"
    settings.openalex_email = "researcher@university.edu"
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "test-password"
    settings.neo4j_database = "neo4j"
    settings.sqlite_telemetry_path = "data/telemetry.sqlite"
    settings.data_dir = "data"
    settings.campaigns_dir = "data/campaigns"
    settings.provenance_crops_dir = "data/provenance/crops"
    settings.telemetry_dir = "data/telemetry"
    settings.log_retention_hours = 24
    settings.embedding_dimensions = 768
    settings.openalex_rate_limit = 9.0
    settings.app_host = "0.0.0.0"
    settings.app_port = 8000
    return settings


@pytest.fixture(autouse=True)
def clean_dependency_overrides() -> AsyncIterator[None]:
    """Automatically clear FastAPI dependency overrides before and after each test."""
    from main import app
    app.dependency_overrides.clear()
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# --- Feature 008 Presentation Test Fixtures (Constitution A59) ---


@pytest.fixture
def mock_presentation_project_facts() -> dict[str, Any]:
    """Seeded epistemic project facts fixture for test-campaign-001."""
    return {
        "project_id": "test-campaign-001",
        "project_name": "Graph-Centric Dual-Loop Architecture",
        "domain": "Computer Science / Artificial Intelligence",
        "description": "Autonomous literature review system leveraging Neo4j and multi-agent systems.",
        "creation_date": "2026-09-01T10:00:00Z",
        "workflow_stage": "stage_4_synthesis",
        "research_questions": [
            {
                "question_id": "rq-001",
                "rq_id": "rq-001",
                "text": "How does graph-native indexing eliminate citation hallucinations?",
                "finer_text": "How does graph-native indexing eliminate citation hallucinations?",
                "coverage_score": 0.88,
                "status": "grounded",
                "grounded_paper_count": 12,
            },
            {
                "question_id": "rq-002",
                "rq_id": "rq-002",
                "text": "What is the optimal dual-loop routing latency for multi-agent synthesis?",
                "finer_text": "What is the optimal dual-loop routing latency for multi-agent synthesis?",
                "coverage_score": 0.65,
                "status": "open_frontier",
                "grounded_paper_count": 4,
            },
        ],
        "scientometrics": {
            "total_papers": 42,
            "total_citations": 1845,
            "unique_authors": 112,
            "year_distribution": {2021: 4, 2022: 9, 2023: 15, 2024: 14},
            "top_venues": [{"venue": "NeurIPS", "count": 12}, {"venue": "ICML", "count": 8}],
            "top_authors": [{"author": "Vaswani, A.", "count": 5}],
            "landmark_papers": [
                {
                    "doi": "10.1145/3292500.3330919",
                    "title": "Graph Neural Networks: A Review of Methods and Applications",
                    "year": 2019,
                    "venue": "KDD",
                    "external_citations": 5000,
                    "in_graph_citations": 14,
                    "summary": "Foundational survey of GNN models.",
                }
            ],
        },
        "synthesis_matrices": [
            {
                "section_id": "sec-01",
                "section_title": "Taxonomy of Epistemic Graph Architectures",
                "dimensions": ["Graph Model", "Query Engine", "Hallucination Control"],
                "matrix_markdown": "| Model | Query Engine | Hallucination Control |\n|---|---|---|\n| ALRS | Neo4j Cypher | 0.0% CHR |",
                "paper_count": 8,
            }
        ],
        "svpl_pathways": [
            {
                "from_doi": "10.1145/3292500.3330919",
                "to_doi": "10.1145/3394486.3403063",
                "intermediate_dois": ["10.1109/TKDE.2020.3012345"],
                "bridge_mechanism": "steiner",
                "hop_count": 2,
                "confidence": 0.95,
            }
        ],
        "empty_library_warning": False,
    }


@pytest.fixture
def mock_empty_campaign_facts() -> dict[str, Any]:
    """Zero-paper scoping campaign fixture for empty-campaign-002."""
    return {
        "project_id": "empty-campaign-002",
        "project_name": "Zero-Paper Inception Campaign",
        "domain": "Computer Science / Artificial Intelligence",
        "description": "Scoping phase campaign with no ingested literature.",
        "creation_date": "2026-09-01T00:00:00Z",
        "workflow_stage": "stage_1_scoping",
        "research_questions": [
            {
                "question_id": "rq-empty-1",
                "rq_id": "rq-empty-1",
                "text": "What are the initial hypotheses?",
                "finer_text": "What are the initial hypotheses?",
                "coverage_score": 0.0,
                "status": "open_frontier",
                "grounded_paper_count": 0,
            }
        ],
        "scientometrics": {
            "total_papers": 0,
            "total_citations": 0,
            "unique_authors": 0,
            "year_distribution": {},
            "top_venues": [],
            "top_authors": [],
            "landmark_papers": [],
        },
        "synthesis_matrices": [],
        "svpl_pathways": [],
        "empty_library_warning": True,
    }


@pytest.fixture
def mock_presentation_neo4j_service() -> AsyncMock:
    """Mock Neo4j service with realistic responses for presentation queries."""
    service = AsyncMock()
    service.connect = AsyncMock()
    service.close = AsyncMock()
    service.health_check = AsyncMock(return_value=True)

    KNOWN_DOIS = {
        "10.1145/3292500.3330919": "Graph Neural Networks: A Review of Methods and Applications",
        "10.1145/3394486.3403063": "Heterogeneous Graph Structure Learning",
        "10.1109/tkde.2020.3012345": "Multi-hop Reasoning on Knowledge Graphs",
    }

    async def fake_execute_read(query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = parameters or {}
        project_id = str(params.get("project_id", ""))

        if "UNWIND $candidate_dois" in query:
            candidate_dois = params.get("candidate_dois", [])
            return [
                {
                    "candidate_doi": c_doi,
                    "is_grounded": c_doi.lower() in KNOWN_DOIS,
                    "verified_title": KNOWN_DOIS.get(c_doi.lower(), ""),
                }
                for c_doi in candidate_dois
            ]

        if project_id == "empty-campaign-002":
            if "HAS_RESEARCH_QUESTION" in query:
                return [{
                    "project_id": "empty-campaign-002",
                    "project_name": "Zero-Paper Inception Campaign",
                    "domain": "Computer Science / Artificial Intelligence",
                    "description": "Scoping phase campaign with no ingested literature.",
                    "creation_date": "2026-09-01T00:00:00Z",
                    "workflow_stage": "stage_1_scoping",
                    "research_questions": [{
                        "rq_id": "rq-empty-1",
                        "finer_text": "What are the initial hypotheses?",
                        "coverage_score": 0.0,
                        "status": "open_frontier",
                        "grounded_paper_count": 0,
                    }],
                }]
            if "total_papers" in query:
                return [{
                    "total_papers": 0,
                    "total_citations": 0,
                    "unique_authors": 0,
                    "year_distribution": [],
                    "top_venues": [],
                    "top_authors": [],
                }]
            return []

        if project_id == "test-campaign-001":
            if "HAS_RESEARCH_QUESTION" in query:
                return [{
                    "project_id": "test-campaign-001",
                    "project_name": "Graph-Centric Dual-Loop Architecture",
                    "domain": "Computer Science / Artificial Intelligence",
                    "description": "Autonomous literature review system leveraging Neo4j and multi-agent systems.",
                    "creation_date": "2026-09-01T10:00:00Z",
                    "workflow_stage": "stage_4_synthesis",
                    "research_questions": [
                        {
                            "rq_id": "rq-001",
                            "finer_text": "How does graph-native indexing eliminate citation hallucinations?",
                            "coverage_score": 0.88,
                            "status": "grounded",
                            "grounded_paper_count": 12,
                        },
                        {
                            "rq_id": "rq-002",
                            "finer_text": "What is the optimal dual-loop routing latency for multi-agent synthesis?",
                            "coverage_score": 0.65,
                            "status": "open_frontier",
                            "grounded_paper_count": 4,
                        },
                    ],
                }]
            if "total_papers" in query:
                return [{
                    "total_papers": 42,
                    "total_citations": 1845,
                    "unique_authors": 112,
                    "year_distribution": [
                        {"year": 2021, "count": 4},
                        {"year": 2022, "count": 9},
                        {"year": 2023, "count": 15},
                        {"year": 2024, "count": 14},
                    ],
                    "top_venues": [{"venue": "NeurIPS", "count": 12}, {"venue": "ICML", "count": 8}],
                    "top_authors": [{"author": "Vaswani, A.", "count": 5}],
                }]
            if "in_graph_citations" in query:
                return [{
                    "doi": "10.1145/3292500.3330919",
                    "title": "Graph Neural Networks: A Review of Methods and Applications",
                    "year": 2019,
                    "venue": "KDD",
                    "external_citations": 5000,
                    "in_graph_citations": 14,
                    "summary": "Foundational survey of GNN models.",
                }]
            if "HAS_MATRIX" in query or "HAS_SYNTHESIS_MATRIX" in query:
                return [{
                    "section_id": "sec-01",
                    "section_title": "Taxonomy of Epistemic Graph Architectures",
                    "dimensions": ["Graph Model", "Query Engine", "Hallucination Control"],
                    "matrix_markdown": "| Model | Query Engine | Hallucination Control |\n|---|---|---|\n| ALRS | Neo4j Cypher | 0.0% CHR |",
                    "paper_count": 8,
                }]
            if "BRIDGES" in query:
                return [{
                    "from_doi": "10.1145/3292500.3330919",
                    "to_doi": "10.1145/3394486.3403063",
                    "intermediate_dois": ["10.1109/TKDE.2020.3012345"],
                    "bridge_mechanism": "steiner",
                    "hop_count": 2,
                }]

        return []

    service.execute_read = AsyncMock(side_effect=fake_execute_read)
    service.execute_write = AsyncMock(return_value=[])
    service.execute_query = AsyncMock(side_effect=fake_execute_read)
    return service

