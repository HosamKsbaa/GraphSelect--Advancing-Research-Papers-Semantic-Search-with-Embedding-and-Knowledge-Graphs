"""Shared test fixtures for ALRS v2 backend tests."""
from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from models.paper import AuthorCreate, PaperCreate, PaperRead, VenueCreate
from models.session import SearchMode, SearchRequest, SessionStatus


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
    """Mock MySQL service with common method stubs."""
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
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "test-password"
    settings.mysql_host = "localhost"
    settings.mysql_port = 3306
    settings.mysql_user = "alrs"
    settings.mysql_password = "test-password"
    settings.mysql_database = "alrs"
    settings.log_retention_hours = 24
    settings.embedding_dimensions = 768
    settings.openalex_rate_limit = 9.0
    settings.app_host = "0.0.0.0"
    settings.app_port = 8000
    return settings
