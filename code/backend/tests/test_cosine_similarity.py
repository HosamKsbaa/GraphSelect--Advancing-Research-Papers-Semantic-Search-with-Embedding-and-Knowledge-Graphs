"""Tests for Neo4j cosine similarity computation."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from core.db.neo4j_service import Neo4jService


@pytest.mark.asyncio
async def test_compute_similarities_query() -> None:
    """Test compute_similarities Cypher query structure and parameters."""
    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    
    # Mock execute_read to return a mock result list
    mock_records = [
        {"doi": "10.1234/paper1", "question": "Question 1", "score": 0.85},
        {"doi": "10.1234/paper2", "question": "Question 2", "score": 0.72},
    ]
    service.execute_read = AsyncMock(return_value=mock_records)
    
    # Run connect mock so driver property does not fail
    with patch("core.db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_gdb.driver.return_value = mock_driver
        await service.connect()

        result = await service.compute_similarities("session-123", 0.65)
        
        # Verify execute_read called with expected parameters
        service.execute_read.assert_called_once()
        args, kwargs = service.execute_read.call_args
        
        assert "db.index.vector.queryNodes" in args[0]
        params = args[1]
        assert "session_id" in params
        assert "threshold" in params
        assert params["session_id"] == "session-123"
        assert params["threshold"] == 0.65
        
        assert len(result) == 2
        assert result[0]["doi"] == "10.1234/paper1"
        assert result[0]["score"] == 0.85
