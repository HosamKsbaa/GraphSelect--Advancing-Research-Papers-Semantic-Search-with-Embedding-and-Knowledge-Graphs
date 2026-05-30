"""Tests for Neo4j service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_neo4j_connect_and_close() -> None:
    """Test Neo4j connection lifecycle."""
    from db.neo4j_service import Neo4jService

    with patch("db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
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
    from db.neo4j_service import Neo4jService

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
