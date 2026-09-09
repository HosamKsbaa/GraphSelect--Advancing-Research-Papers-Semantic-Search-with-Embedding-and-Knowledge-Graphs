"""Empirical Adversarial Test Suite for Relational Primitives & Bridge Materialization.

Validates:
1. OpenAlex Relational Primitives URL formation and encoding.
2. Reference chunking bounds (<= 50 candidate IDs) and URL length safety.
3. Neo4j Layer 4 Cypher bridge materialization:
   - Reproduction of CypherSyntaxError on current MATERIALIZE_PATHWAY_CYPHER
   - Verification of corrected Cypher query on live Neo4j
   - DOI fallback to openalex_id preventing paper_doi_unique collisions
   - Multi-hop :CITES chain and [:BRIDGES] edge properties
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from config import Settings
from core.clients.openalex_client import OpenAlexService
from core.db.neo4j_service import Neo4jService
from features.ranking.svpl_models import BridgeMechanism, BridgeNodeSummary
from features.ranking.svpl_service import (
    DIRECT_BRIDGE_CYPHER,
    MATERIALIZE_PATHWAY_CYPHER,
    SVPLService,
    _build_materialize_params,
    _build_path_node_dicts,
)

OLD_INVALID_SYNTAX_CYPHER = (
    "UNWIND $path_nodes AS node\n"
    "CALL {\n"
    "    WITH node\n"
    "    WHERE node.doi IS NOT NULL\n"
    "    MERGE (p:Paper {doi: node.doi})\n"
    "    ON CREATE SET\n"
    "        p.openalex_id = node.openalex_id,\n"
    "        p.title = node.title,\n"
    "        p.year = node.year,\n"
    "        p.cited_by_count = node.cited_by_count,\n"
    "        p.is_stub = coalesce(node.is_stub, false),\n"
    "        p.is_bridge = true,\n"
    "        p.can_expand_deeply = false,\n"
    "        p.run_id = $run_id,\n"
    "        p.created_in_stage = $created_in_stage,\n"
    "        p.created_at = datetime()\n"
    "    ON MATCH SET\n"
    "        p.openalex_id = coalesce(p.openalex_id, node.openalex_id),\n"
    "        p.is_bridge = true,\n"
    "        p.title = coalesce(p.title, node.title),\n"
    "        p.run_id = coalesce(p.run_id, $run_id),\n"
    "        p.created_in_stage = coalesce(p.created_in_stage, $created_in_stage),\n"
    "        p.updated_at = datetime()\n"
    "    RETURN p\n"
    "    UNION\n"
    "    WITH node\n"
    "    WHERE node.doi IS NULL AND node.openalex_id IS NOT NULL\n"
    "    MERGE (p:Paper {openalex_id: node.openalex_id})\n"
    "    ON CREATE SET\n"
    "        p.title = node.title,\n"
    "        p.year = node.year,\n"
    "        p.cited_by_count = node.cited_by_count,\n"
    "        p.is_stub = coalesce(node.is_stub, false),\n"
    "        p.is_bridge = true,\n"
    "        p.can_expand_deeply = false,\n"
    "        p.run_id = $run_id,\n"
    "        p.created_in_stage = $created_in_stage,\n"
    "        p.created_at = datetime()\n"
    "    ON MATCH SET\n"
    "        p.is_bridge = true,\n"
    "        p.title = coalesce(p.title, node.title),\n"
    "        p.run_id = coalesce(p.run_id, $run_id),\n"
    "        p.created_in_stage = coalesce(p.created_in_stage, $created_in_stage),\n"
    "        p.updated_at = datetime()\n"
    "    RETURN p\n"
    "}\n"
    "WITH count(*) AS _nodes_merged\n"
    "UNWIND $edges AS edge\n"
    "MATCH (from:Paper)\n"
    "WHERE (from.doi IS NOT NULL AND from.doi = edge.from_id) OR (from.openalex_id = edge.from_id)\n"
    "MATCH (to:Paper)\n"
    "WHERE (to.doi IS NOT NULL AND to.doi = edge.to_id) OR (to.openalex_id = edge.to_id)\n"
    "MERGE (from)-[r:CITES]->(to)\n"
    "ON CREATE SET r.discovered_in_tier = $tier, r.run_id = $run_id,\n"
    "r.created_in_stage = $created_in_stage, r.created_at = datetime()\n"
    "WITH count(*) AS _edges_merged\n"
    "MATCH (source:Paper)\n"
    "WHERE ($source_doi IS NOT NULL AND source.doi = $source_doi)\n"
    "   OR ($source_openalex_id IS NOT NULL AND source.openalex_id = $source_openalex_id)\n"
    "MATCH (target:Paper)\n"
    "WHERE ($target_doi IS NOT NULL AND target.doi = $target_doi)\n"
    "   OR ($target_openalex_id IS NOT NULL AND target.openalex_id = $target_openalex_id)\n"
    "MERGE (source)-[b:BRIDGES {mechanism: $mechanism}]->(target)\n"
    "SET b.hop_distance = $hop_distance,\n"
    "    b.intermediate_nodes = [n IN $path_nodes | coalesce(n.doi, n.openalex_id)],\n"
    "    b.confidence = $confidence,\n"
    "    b.discovered_tier = $tier,\n"
    "    b.run_id = $run_id,\n"
    "    b.created_in_stage = $created_in_stage,\n"
    "    b.updated_at = datetime();"
)

CORRECTED_MATERIALIZE_CYPHER = MATERIALIZE_PATHWAY_CYPHER


async def _get_live_neo4j() -> Neo4jService | None:
    """Connect to live Neo4j service or return None if unreachable."""
    for pwd in ["changeme", Settings().neo4j_password]:
        try:
            svc = Neo4jService(uri="bolt://localhost:7687", user="neo4j", password=pwd)
            await svc.connect()
            return svc
        except Exception:
            continue
    return None


# ==============================================================================
# 1. OpenAlex Relational Primitives URL Formation & Encoding
# ==============================================================================

@pytest.mark.asyncio
async def test_openalex_primitives_filter_url_generation() -> None:
    """Validate filter parameter generation for all 4 two-hop relational primitives."""
    service = OpenAlexService(api_key="")
    with patch.object(service, "_query_relational_filter", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        await service.find_2hop_directed("W100", "W200")
        assert mock_q.call_args[0][0] == "cited_by:W100,cites:W200"

        await service.find_2hop_reverse("W100", "W200")
        assert mock_q.call_args[0][0] == "cites:W100,cited_by:W200"

        await service.find_bibliographic_coupling("W100", "W200")
        assert mock_q.call_args[0][0] == "cited_by:W100,cited_by:W200"

        await service.find_co_citation("W100", "W200")
        assert mock_q.call_args[0][0] == "cites:W100,cites:W200"
    await service.close()


@pytest.mark.asyncio
async def test_openalex_primitives_complex_dois_and_urls() -> None:
    """Validate DOI prefixing and URL stripping in filter parameters."""
    service = OpenAlexService(api_key="")
    with patch.object(service, "_query_relational_filter", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        await service.find_2hop_directed("https://doi.org/10.1145/3292500", "doi:10.1016/j.artint.2023")
        assert mock_q.call_args[0][0] == "cited_by:doi:10.1145/3292500,cites:doi:10.1016/j.artint.2023"

        await service.find_2hop_directed("https://openalex.org/W999", "10.1000/182")
        assert mock_q.call_args[0][0] == "cited_by:W999,cites:doi:10.1000/182"
    await service.close()


# ==============================================================================
# 2. OpenAlex Reference Chunking & URL Length Safety
# ==============================================================================

def test_openalex_reference_chunking_url_length_bounds() -> None:
    """Verify that a 50-ID chunk produces an HTTP GET URL strictly <= 2048 chars."""
    client = httpx.AsyncClient(base_url="https://api.openalex.org")
    dois = [f"doi:10.1145/{3000000 + i}" for i in range(50)]
    filter_str = f"cited_by:{'|'.join(dois)},cites:doi:10.1145/3292500"
    req = client.build_request("GET", "/works", params={
        "filter": filter_str, "per_page": 25,
        "select": "id,doi,title,publication_year,cited_by_count",
    })
    assert len(str(req.url)) <= 2048
    assert len(str(req.url)) > 500


@pytest.mark.asyncio
async def test_openalex_reference_chunking_exact_batches() -> None:
    """Verify chunking splits candidate lists into ceil(N/50) distinct queries."""
    service = OpenAlexService(api_key="")
    with patch.object(service, "_query_relational_filter", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        # 50 refs -> exactly 1 batch
        await service.batch_pipe_disjunctive_3hop([f"W{i}" for i in range(50)], "W_tgt")
        assert mock_q.call_count == 1

        mock_q.reset_mock()
        # 51 refs -> exactly 2 batches
        await service.batch_pipe_disjunctive_3hop([f"W{i}" for i in range(51)], "W_tgt")
        assert mock_q.call_count == 2

        mock_q.reset_mock()
        # 125 refs -> exactly 3 batches
        await service.batch_pipe_disjunctive_3hop([f"W{i}" for i in range(125)], "W_tgt")
        assert mock_q.call_count == 3
    await service.close()


@pytest.mark.asyncio
async def test_openalex_reference_chunking_filters_invalid_refs() -> None:
    """Verify empty strings, None, and whitespace items are pruned from batching."""
    service = OpenAlexService(api_key="")
    with patch.object(service, "_query_relational_filter", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        res = await service.batch_pipe_disjunctive_3hop(["", "  ", None], "W_tgt")  # type: ignore[list-item]
        assert res == []
        assert mock_q.call_count == 0

        await service.batch_pipe_disjunctive_3hop(["W1", "", "  ", "W2"], "W_tgt")
        assert mock_q.call_count == 1
        filter_arg = mock_q.call_args[0][0]
        assert filter_arg == "cited_by:W1|W2,cites:W_tgt"
    await service.close()


def test_openalex_parse_relational_work_edge_cases() -> None:
    """Test standardized dictionary extraction with missing and complete fields."""
    item = {
        "id": "https://openalex.org/W12345", "doi": "https://doi.org/10.1145/3292500",
        "title": "  A Unified Model  ", "publication_year": 2023, "cited_by_count": 42,
    }
    p = OpenAlexService._parse_relational_work(item)
    assert p["openalex_id"] == "W12345"
    assert p["doi"] == "10.1145/3292500"
    assert p["title"] == "A Unified Model"
    assert p["year"] == 2023
    assert p["cited_by_count"] == 42

    empty_p = OpenAlexService._parse_relational_work({})
    assert empty_p["openalex_id"] is None
    assert empty_p["doi"] is None
    assert empty_p["title"] == ""
    assert empty_p["cited_by_count"] == 0


# ==============================================================================
# 3. SVPL Service Edge Construction Unit Tests
# ==============================================================================

def test_svpl_build_pathway_edges_two_hop() -> None:
    """Two-hop pathway produces two sequential CITES edges."""
    svpl = SVPLService()
    u = BridgeNodeSummary(openalex_id="W_mid", doi="10.1/mid", title="Mid")
    edges = svpl._build_pathway_edges("10.1/src", "10.1/tgt", [u])
    assert len(edges) == 2
    assert edges[0] == {"from_id": "10.1/src", "to_id": "10.1/mid"}
    assert edges[1] == {"from_id": "10.1/mid", "to_id": "10.1/tgt"}


def test_svpl_build_pathway_edges_three_hop() -> None:
    """Three-hop pathway produces three sequential CITES edges."""
    svpl = SVPLService()
    u1 = BridgeNodeSummary(openalex_id="W1", title="Mid 1")
    u2 = BridgeNodeSummary(openalex_id="W2", doi="10.1/u2", title="Mid 2")
    edges = svpl._build_pathway_edges("10.1/src", "10.1/tgt", [u1, u2])
    assert len(edges) == 3
    assert edges[0] == {"from_id": "10.1/src", "to_id": "W1"}
    assert edges[1] == {"from_id": "W1", "to_id": "10.1/u2"}
    assert edges[2] == {"from_id": "10.1/u2", "to_id": "10.1/tgt"}


# ==============================================================================
# 4. Neo4j Layer 4 Live Cypher Materialization Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_live_neo4j_direct_bridge_cypher() -> None:
    """Verify DIRECT_BRIDGE_CYPHER merges [:BRIDGES] edge between existing papers."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    uid = uuid.uuid4().hex[:6]
    s_doi, t_doi = f"10.1/ds_{uid}", f"10.1/dt_{uid}"
    await neo4j.execute_write("MERGE (s:Paper {doi: $s}) MERGE (t:Paper {doi: $t})", {"s": s_doi, "t": t_doi})
    params = {
        "source_doi": s_doi, "target_doi": t_doi, "source_openalex_id": None,
        "target_openalex_id": None, "mechanism": "directed_2hop", "hop_distance": 1,
        "confidence": 1.0, "tier": 1, "run_id": f"run_{uid}", "created_in_stage": 2,
    }
    await neo4j.execute_write(DIRECT_BRIDGE_CYPHER, params)
    res = await neo4j.execute_read(
        "MATCH (s:Paper {doi: $s})-[b:BRIDGES]->(t:Paper {doi: $t}) RETURN properties(b) as p",
        {"s": s_doi, "t": t_doi},
    )
    assert len(res) == 1 and res[0]["p"]["mechanism"] == "directed_2hop"
    await neo4j.execute_write("MATCH (p:Paper) WHERE p.doi IN [$s, $t] DETACH DELETE p", {"s": s_doi, "t": t_doi})
    await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_materialize_pathway_cypher_syntax_error_reproduced() -> None:
    """Empirically prove pre-remediation Cypher query throws CypherSyntaxError on Neo4j."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    params = {
        "source_doi": "10.1/s", "target_doi": "10.1/t", "source_openalex_id": None,
        "target_openalex_id": None, "mechanism": "directed_2hop", "hop_distance": 2,
        "confidence": 0.95, "tier": 1, "run_id": "r1", "created_in_stage": 2,
        "path_nodes": [{"doi": "10.1/m", "openalex_id": "W1", "title": "M", "year": 2022, "cited_by_count": 10, "is_stub": True}],
        "edges": [{"from_id": "10.1/s", "to_id": "10.1/m"}, {"from_id": "10.1/m", "to_id": "10.1/t"}],
    }
    with pytest.raises(Exception) as exc_info:
        await neo4j.execute_write(OLD_INVALID_SYNTAX_CYPHER, params)
    err_str = str(exc_info.value)
    assert "Importing WITH should consist only of simple references to outside variables" in err_str
    await neo4j.close()


async def _verify_materialized_graph(
    neo4j: Neo4jService, run_id: str, s_doi: str, t_doi: str, m_doi: str
) -> None:
    """Verify :CITES edges and [:BRIDGES] properties in Neo4j."""
    cites = await neo4j.execute_read(
        "MATCH (p:Paper)-[r:CITES]->(p2:Paper) WHERE r.run_id = $run RETURN count(r) as cnt",
        {"run": run_id},
    )
    assert cites[0]["cnt"] == 2
    b_res = await neo4j.execute_read(
        "MATCH (s:Paper {doi: $s})-[b:BRIDGES]->(t:Paper {doi: $t}) RETURN properties(b) as p",
        {"s": s_doi, "t": t_doi},
    )
    assert len(b_res) == 1
    assert b_res[0]["p"]["mechanism"] == "directed_2hop"
    assert b_res[0]["p"]["intermediate_nodes"] == [m_doi]


@pytest.mark.asyncio
async def test_live_neo4j_corrected_materialize_pathway_execution() -> None:
    """Verify production Cypher query successfully merges nodes, :CITES chain, and [:BRIDGES]."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    uid = uuid.uuid4().hex[:6]
    s_doi, t_doi, m_doi, m_oa = f"10.1/s_{uid}", f"10.1/t_{uid}", f"10.1/m_{uid}", f"W_m_{uid}"
    await neo4j.execute_write("MERGE (s:Paper {doi: $s}) MERGE (t:Paper {doi: $t})", {"s": s_doi, "t": t_doi})
    params = {
        "source_doi": s_doi, "target_doi": t_doi, "source_openalex_id": None,
        "target_openalex_id": None, "mechanism": "directed_2hop", "hop_distance": 2,
        "confidence": 0.95, "tier": 1, "run_id": f"run_{uid}", "created_in_stage": 2,
        "path_nodes": [{"doi": m_doi, "openalex_id": m_oa, "title": "Mid", "year": 2022, "cited_by_count": 10, "is_stub": True}],
        "edges": [{"from_id": s_doi, "to_id": m_doi}, {"from_id": m_doi, "to_id": t_doi}],
    }
    await neo4j.execute_write(MATERIALIZE_PATHWAY_CYPHER, params)
    await _verify_materialized_graph(neo4j, f"run_{uid}", s_doi, t_doi, m_doi)
    await neo4j.execute_write("MATCH (p:Paper) WHERE p.run_id = $run OR p.doi IN [$s, $t] DETACH DELETE p", {"run": f"run_{uid}", "s": s_doi, "t": t_doi})
    await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_paper_doi_unique_constraint_fallback() -> None:
    """Verify intermediate nodes with NULL DOI merge on openalex_id without violating constraint."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    uid = uuid.uuid4().hex[:6]
    s_doi, t_doi = f"10.1/s_{uid}", f"10.1/t_{uid}"
    nodoi_1, nodoi_2 = f"W_nodoi1_{uid}", f"W_nodoi2_{uid}"
    await neo4j.execute_write("MERGE (s:Paper {doi: $s}) MERGE (t:Paper {doi: $t})", {"s": s_doi, "t": t_doi})
    params = {
        "source_doi": s_doi, "target_doi": t_doi, "source_openalex_id": None,
        "target_openalex_id": None, "mechanism": "pipe_disjunctive_3hop", "hop_distance": 3,
        "confidence": 0.85, "tier": 1, "run_id": f"run_{uid}", "created_in_stage": 2,
        "path_nodes": [
            {"doi": None, "openalex_id": nodoi_1, "title": "No DOI 1", "year": 2021, "cited_by_count": 2, "is_stub": True},
            {"doi": None, "openalex_id": nodoi_2, "title": "No DOI 2", "year": 2022, "cited_by_count": 4, "is_stub": True},
        ],
        "edges": [{"from_id": s_doi, "to_id": nodoi_1}, {"from_id": nodoi_1, "to_id": nodoi_2}, {"from_id": nodoi_2, "to_id": t_doi}],
    }
    await neo4j.execute_write(MATERIALIZE_PATHWAY_CYPHER, params)
    n1 = await neo4j.execute_read("MATCH (p:Paper {openalex_id: $oa}) RETURN p.doi as doi", {"oa": nodoi_1})
    assert len(n1) == 1 and n1[0]["doi"] is None
    await neo4j.execute_write("MATCH (p:Paper) WHERE p.run_id = $run OR p.doi IN [$s, $t] DETACH DELETE p", {"run": f"run_{uid}", "s": s_doi, "t": t_doi})
    await neo4j.close()
