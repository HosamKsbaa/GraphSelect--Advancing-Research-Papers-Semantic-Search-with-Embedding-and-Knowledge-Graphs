"""Unit and schema compatibility tests for PaperRead and DI providers (T052 / Milestone M6).

Verifies:
1. PaperRead backwards compatibility with legacy payloads.
2. Default values for is_stub, is_bridge, can_expand_deeply, and is_retracted.
3. Explicit value retention and JSON round-trip serialization.
4. Zero RAM policy: embedding field MUST NOT exist on PaperRead (Constitution A5).
5. FastAPI dependency injection providers in core/dependencies.py (T058).

Conforms to Constitution v2.2.1 (C2, C5, C7, C8, C9, A5, A6).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
import pytest

from core.dependencies import (
    get_ingestion_service,
    get_matrix_service,
    get_remediation_service,
    get_svpl_service,
)
from features.drafting.matrix_service import MatrixService
from features.gap_analysis.remediation_service import RemediationService
from features.ingestion.ingestion_service import IngestionService
from features.ranking.svpl_service import SVPLService
from features.retrieval.models import (
    AuthorRead,
    PaperCreate,
    PaperRead,
    PaperSummary,
    VenueRead,
)


def _make_legacy_paper_dict() -> dict[str, Any]:
    """Return dictionary simulating legacy API payload without new enhancement fields."""
    return {
        "doi": "10.1145/3442381.3449834",
        "title": "Deep Learning on Graphs",
        "abstract": "Comprehensive graph review.",
        "year": 2021,
        "cited_by_count": 120,
        "openalex_id": "W3128456789",
        "publication_date": "2021-04-19",
        "source": "openalex",
        "authors": [{"name": "Jane Doe", "paper_count": 5}],
        "venue": {"name": "ACM WebConf", "paper_count": 50},
        "keywords": ["graphs", "embeddings"],
    }


def test_paper_read_defaults_for_enhancement_fields() -> None:
    """Verify PaperRead defaults for new fields ensure 100% backward compatibility."""
    paper = PaperRead(
        doi="10.1000/182",
        title="Minimal Paper",
    )
    assert paper.is_stub is False
    assert paper.is_bridge is False
    assert paper.can_expand_deeply is True
    assert paper.is_retracted is False


def test_paper_read_parses_legacy_payload_seamlessly() -> None:
    """Verify legacy dictionary without new fields instantiates PaperRead correctly."""
    legacy_data = _make_legacy_paper_dict()
    paper = PaperRead(**legacy_data)
    assert paper.doi == "10.1145/3442381.3449834"
    assert paper.title == "Deep Learning on Graphs"
    assert paper.is_stub is False
    assert paper.is_bridge is False
    assert paper.can_expand_deeply is True
    assert paper.is_retracted is False


def test_paper_read_explicit_enhancement_fields() -> None:
    """Verify PaperRead preserves explicitly configured enhancement fields."""
    paper = PaperRead(
        doi="10.1000/custom",
        title="Bridge Stub Paper",
        is_stub=True,
        is_bridge=True,
        can_expand_deeply=False,
        is_retracted=True,
    )
    assert paper.is_stub is True
    assert paper.is_bridge is True
    assert paper.can_expand_deeply is False
    assert paper.is_retracted is True


def test_paper_read_json_roundtrip_serialization() -> None:
    """Verify JSON serialization and deserialization retains all fields."""
    paper = PaperRead(
        doi="10.1000/roundtrip",
        title="Serialization Test",
        is_stub=True,
        is_bridge=False,
        can_expand_deeply=True,
        is_retracted=False,
    )
    json_str = paper.model_dump_json()
    reloaded = PaperRead.model_validate_json(json_str)
    assert reloaded == paper
    raw_dict = paper.model_dump(mode="json")
    assert raw_dict["is_stub"] is True
    assert raw_dict["can_expand_deeply"] is True


def test_paper_read_zero_ram_embedding_policy() -> None:
    """Verify PaperRead complies with zero-RAM policy (MUST NOT have embedding field)."""
    assert "embedding" not in PaperRead.model_fields
    assert "embeddings" not in PaperRead.model_fields
    paper = PaperRead(doi="10.1000/zero_ram", title="Zero RAM Test")
    assert not hasattr(paper, "embedding")


def test_paper_create_and_summary_compatibility() -> None:
    """Verify interoperability with PaperCreate and PaperSummary."""
    summary = PaperSummary(
        doi="10.1000/summary",
        title="Summary Paper",
        year=2024,
        cited_by_count=10,
        authors=["Alice", "Bob"],
    )
    assert summary.doi == "10.1000/summary"
    create_model = PaperCreate(
        doi="10.1000/valid_doi",
        title="Paper Create",
        year=2023,
    )
    assert create_model.doi == "10.1000/valid_doi"


def test_dependency_provider_ingestion_service() -> None:
    """Verify get_ingestion_service constructs IngestionService instance."""
    mock_neo4j = MagicMock()
    mock_openalex = MagicMock()
    mock_gemini = MagicMock()
    service = get_ingestion_service(
        neo4j=mock_neo4j, openalex=mock_openalex, gemini=mock_gemini,
    )
    assert isinstance(service, IngestionService)
    assert service.neo4j is mock_neo4j
    assert service.openalex is mock_openalex


def test_dependency_provider_svpl_service() -> None:
    """Verify get_svpl_service constructs SVPLService instance."""
    mock_neo4j = MagicMock()
    mock_openalex = MagicMock()
    mock_gemini = MagicMock()
    service = get_svpl_service(
        neo4j=mock_neo4j, openalex=mock_openalex, gemini=mock_gemini,
    )
    assert isinstance(service, SVPLService)
    assert service._neo4j is mock_neo4j
    assert service._openalex is mock_openalex


def test_dependency_provider_remediation_service() -> None:
    """Verify get_remediation_service constructs RemediationService instance."""
    mock_neo4j = MagicMock()
    mock_openalex = MagicMock()
    service = get_remediation_service(
        neo4j=mock_neo4j, openalex=mock_openalex,
    )
    assert isinstance(service, RemediationService)
    assert service.neo4j is mock_neo4j
    assert service.openalex is mock_openalex


def test_dependency_provider_matrix_service() -> None:
    """Verify get_matrix_service constructs MatrixService instance."""
    mock_neo4j = MagicMock()
    service = get_matrix_service(neo4j=mock_neo4j)
    assert isinstance(service, MatrixService)
    assert service.neo4j is mock_neo4j
