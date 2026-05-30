"""Tests for Neo4j PageRank (GDS and NetworkX fallbacks)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from db.neo4j_service import Neo4jService


@pytest.mark.asyncio
async def test_compute_pagerank_gds_success() -> None:
    """Test successful PageRank execution using Neo4j GDS."""
    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    
    # Mock calls
    # Call 1: gds.graph.project (write)
    # Call 2: gds.pageRank.stream (read)
    # Call 3: gds.graph.drop (write)
    service.execute_write = AsyncMock(return_value=[])
    service.execute_read = AsyncMock(return_value=[
        {"doi": "10.1234/p1", "score": 2.0},
        {"doi": "10.1234/p2", "score": 1.0},
    ])
    
    with patch("db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_gdb.driver.return_value = mock_driver
        await service.connect()

        result = await service.compute_pagerank("session-123", iterations=20, damping=0.85)
        
        # Verify GDS Cypher calls
        assert service.execute_write.call_count == 2
        service.execute_read.assert_called_once()
        assert "gds.pageRank.stream" in service.execute_read.call_args[0][0]
        
        # Verify normalization to [0.0, 1.0]
        # min_s = 1.0, max_s = 2.0 -> p1 = (2-1)/(2-1) = 1.0, p2 = (1-1)/(2-1) = 0.0
        assert result["10.1234/p1"] == 1.0
        assert result["10.1234/p2"] == 0.0


@pytest.mark.asyncio
async def test_compute_pagerank_networkx_fallback() -> None:
    """Test fallback to pure-Python NetworkX PageRank when GDS throws an exception."""
    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    
    # Simulate GDS failing on graph project
    service.execute_write = AsyncMock(side_effect=Exception("GDS missing"))
    
    # Mock fallback queries
    # Call 1: Fetch DOIs (read)
    # Call 2: Fetch CITES edges (read)
    service.execute_read = AsyncMock(side_effect=[
        [{"doi": "10.1234/p1"}, {"doi": "10.1234/p2"}],  # DOIs
        [{"source": "10.1234/p1", "target": "10.1234/p2"}],  # CITES links
    ])
    
    # Mock networkx module using sys.modules patching
    from unittest.mock import MagicMock
    mock_nx = MagicMock()
    mock_nx.DiGraph = MagicMock()
    # mock pagerank calculation to return scores
    mock_nx.pagerank.return_value = {"10.1234/p1": 0.8, "10.1234/p2": 0.2}
    
    with patch.dict("sys.modules", {"networkx": mock_nx}):
        with patch("db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
            mock_driver = AsyncMock()
            mock_gdb.driver.return_value = mock_driver
            await service.connect()

            result = await service.compute_pagerank("session-123", iterations=20, damping=0.85)
            
            # Verify result contains the nodes from the NetworkX fallback
            assert "10.1234/p1" in result
            assert "10.1234/p2" in result
            assert result["10.1234/p1"] == 1.0  # (0.8 - 0.2)/(0.8 - 0.2) = 1.0
            assert result["10.1234/p2"] == 0.0  # (0.2 - 0.2)/(0.8 - 0.2) = 0.0


@pytest.mark.asyncio
async def test_compute_pagerank_degree_centrality_fallback() -> None:
    """Test fallback to degree centrality if NetworkX also fails or is missing."""
    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")
    
    # Simulate GDS failing
    service.execute_write = AsyncMock(side_effect=Exception("GDS missing"))
    
    # Mock NetworkX Import Failure by patching sys.modules to None
    with patch.dict("sys.modules", {"networkx": None}):
        # Mock degree centrality read query returning degrees
        service.execute_read = AsyncMock(return_value=[
            {"doi": "10.1234/p1", "degree": 5},
            {"doi": "10.1234/p2", "degree": 1},
        ])
        
        with patch("db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
            mock_driver = AsyncMock()
            mock_gdb.driver.return_value = mock_driver
            await service.connect()

            result = await service.compute_pagerank("session-123")
            
            # Verify degree centrality query was executed
            service.execute_read.assert_called_once()
            assert "degree" in service.execute_read.call_args[0][0]
            
            # Verify normalized outputs
            # min = 1, max = 5 -> p1 = (5-1)/4 = 1.0, p2 = 0.0
            assert result["10.1234/p1"] == 1.0
            assert result["10.1234/p2"] == 0.0
