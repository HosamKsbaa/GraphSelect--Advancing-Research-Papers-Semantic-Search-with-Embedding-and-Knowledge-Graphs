"""Tests for Neo4j service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_neo4j_connect_and_close() -> None:
    """Test Neo4j connection lifecycle."""
    from core.db.neo4j_service import Neo4jService

    with patch("core.db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
        await service.connect()

        mock_gdb.driver.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
        )
        mock_driver.verify_connectivity.assert_awaited_once()

        await service.close()
        mock_driver.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_neo4j_driver_not_initialized() -> None:
    """Test accessing driver before connect raises RuntimeError."""
    from core.db.neo4j_service import Neo4jService

    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = service.driver


@pytest.mark.asyncio
async def test_neo4j_health_check_healthy(mock_neo4j_service: AsyncMock) -> None:
    """Test health check returns True when connected."""
    result = await mock_neo4j_service.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_neo4j_execute_read(mock_neo4j_service: AsyncMock) -> None:
    """Test execute_read returns expected data."""
    mock_neo4j_service.execute_read.return_value = [{"doi": "10.1234/test"}]
    result = await mock_neo4j_service.execute_read("MATCH (p:Paper) RETURN p.doi AS doi")
    assert len(result) == 1
    assert result[0]["doi"] == "10.1234/test"


@pytest.mark.asyncio
async def test_neo4j_execute_write(mock_neo4j_service: AsyncMock) -> None:
    """Test execute_write completes without error."""
    mock_neo4j_service.execute_write.return_value = []
    result = await mock_neo4j_service.execute_write(
        "CREATE (p:Paper {doi: $doi})", {"doi": "10.1234/test"}
    )
    assert result == []


def test_normalize_doi() -> None:
    """Test canonical lowercase DOI normalization and prefix stripping."""
    from core.db.neo4j_service import normalize_doi

    assert normalize_doi("https://doi.org/10.1145/3292500.3330964") == "10.1145/3292500.3330964"
    assert normalize_doi("http://doi.org/10.1000/182") == "10.1000/182"
    assert normalize_doi("doi:10.1038/nature12373") == "10.1038/nature12373"
    assert normalize_doi("  10.1145/SAMPLE.DOI  ") == "10.1145/sample.doi"


@pytest.mark.asyncio
async def test_neo4j_layer_and_rollback_methods() -> None:
    """Test Layer 1/2/3 runners and compensating rollback in Neo4jService."""
    from core.db.neo4j_service import Neo4jService

    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    service.execute_write = AsyncMock(return_value=[{"cnt": 3}])  # type: ignore[method-assign]

    # Layer 1
    await service.link_paper_citation("10.1145/A", "10.1145/B", is_seed=True)
    await service.link_paper_author("10.1145/A", "Dr. Jane Doe", "A123", 1)
    await service.link_paper_venue("10.1145/A", "KDD", "V123", "1234-5678")

    # Layer 2
    service.execute_write.return_value = [{"claim_id": "c1", "statement": "Test claim"}]
    claim = await service.create_claim("c1", "10.1145/A", "Test claim", 0.98)
    assert claim["claim_id"] == "c1"
    await service.link_claim_supports("c1", "q1", 0.95)
    await service.link_claim_refutes("c1", "q2", 0.85)
    await service.link_claim_contradiction("c1", "c2", "empirical conflict")
    await service.link_claim_resolution("c1", "c2", "c3")

    # Layer 3
    service.execute_write.return_value = [{"method_id": "m1", "name": "LoRA"}]
    method = await service.create_method("m1", "10.1145/A", "LoRA")
    assert method["name"] == "LoRA"
    service.execute_write.return_value = [{"dataset_id": "d1", "name": "Cora"}]
    dataset = await service.create_dataset("d1", "Cora")
    assert dataset["name"] == "Cora"
    service.execute_write.return_value = [{"result_id": "r1", "score": 0.92}]
    res = await service.create_metric_result("r1", "m1", "d1", "Accuracy", 0.92)
    assert res["score"] == 0.92

    # Workflow state and compensating rollback
    await service.link_campaign_stage_state("camp-1", "sub-1", 1, "scoping", "completed")
    service.execute_write.return_value = [{"cnt": 5}]
    deleted_cnt = await service.rollback_stage_transaction("run-xyz", 2)
    assert deleted_cnt == 5

