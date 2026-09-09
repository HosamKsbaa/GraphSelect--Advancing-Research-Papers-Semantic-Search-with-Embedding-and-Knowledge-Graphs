"""Scientometric-Vector Progressive Ladder (SVPL) Multi-Hop Discovery Service.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C8: Pure Neo4j SSOT, zero MySQL.
- C9: Functions decomposed under 25 lines (SRP & SLAP).
- C11: Clear domain abstractions and predicate booleans.
- A38: OpenAlex polite pool headers.
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Any, Union

from core.clients.openalex_client import OpenAlexService
from core.db.neo4j_service import Neo4jService
from features.ranking.svpl_gating import check_multihop_authorization
from features.ranking.svpl_models import (
    BridgeHopCandidate,
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopAuthorization,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
)

logger = logging.getLogger(__name__)

LAYER0_CYPHER = (
    "OPTIONAL MATCH (source:Paper {doi: $source_doi}) "
    "OPTIONAL MATCH (target:Paper {doi: $target_doi}) "
    "OPTIONAL MATCH direct_path = (source)-[:CITES]-(target) "
    "OPTIONAL MATCH two_hop_path = (source)-[:CITES]-(mid:Paper)-[:CITES]-(target) "
    "RETURN "
    "source IS NOT NULL AS source_exists, "
    "target IS NOT NULL AS target_exists, "
    "CASE "
    "WHEN source IS NULL OR target IS NULL THEN 'missing_nodes' "
    "WHEN direct_path IS NOT NULL THEN 'direct' "
    "WHEN two_hop_path IS NOT NULL THEN 'two_hop' "
    "ELSE 'none' "
    "END AS connection_type, "
    "mid.doi AS intermediate_doi, "
    "mid.openalex_id AS intermediate_openalex_id, "
    "mid.title AS intermediate_title, "
    "mid.year AS intermediate_year, "
    "mid.cited_by_count AS intermediate_cited_by_count, "
    "coalesce(mid.is_stub, false) AS is_stub "
    "LIMIT 1;"
)

MATERIALIZE_PATHWAY_CYPHER = (
    "UNWIND $path_nodes AS node "
    "CALL { "
    "    WITH node "
    "    WITH node WHERE node.doi IS NOT NULL "
    "    MERGE (p:Paper {doi: node.doi}) "
    "    ON CREATE SET "
    "        p.openalex_id = node.openalex_id, "
    "        p.title = node.title, "
    "        p.year = node.year, "
    "        p.cited_by_count = node.cited_by_count, "
    "        p.is_stub = coalesce(node.is_stub, false), "
    "        p.is_bridge = true, "
    "        p.can_expand_deeply = false, "
    "        p.run_id = $run_id, "
    "        p.created_in_stage = $created_in_stage, "
    "        p.created_at = datetime() "
    "    ON MATCH SET "
    "        p.openalex_id = coalesce(p.openalex_id, node.openalex_id), "
    "        p.is_bridge = true, "
    "        p.title = coalesce(p.title, node.title), "
    "        p.run_id = coalesce(p.run_id, $run_id), "
    "        p.created_in_stage = coalesce(p.created_in_stage, $created_in_stage), "
    "        p.updated_at = datetime() "
    "    RETURN p "
    "    UNION "
    "    WITH node "
    "    WITH node WHERE node.doi IS NULL AND node.openalex_id IS NOT NULL "
    "    MERGE (p:Paper {openalex_id: node.openalex_id}) "
    "    ON CREATE SET "
    "        p.title = node.title, "
    "        p.year = node.year, "
    "        p.cited_by_count = node.cited_by_count, "
    "        p.is_stub = coalesce(node.is_stub, false), "
    "        p.is_bridge = true, "
    "        p.can_expand_deeply = false, "
    "        p.run_id = $run_id, "
    "        p.created_in_stage = $created_in_stage, "
    "        p.created_at = datetime() "
    "    ON MATCH SET "
    "        p.is_bridge = true, "
    "        p.title = coalesce(p.title, node.title), "
    "        p.run_id = coalesce(p.run_id, $run_id), "
    "        p.created_in_stage = coalesce(p.created_in_stage, $created_in_stage), "
    "        p.updated_at = datetime() "
    "    RETURN p "
    "} "
    "WITH count(*) AS _nodes_merged "
    "UNWIND $edges AS edge "
    "MATCH (from:Paper) "
    "WHERE (from.doi IS NOT NULL AND from.doi = edge.from_id) OR (from.openalex_id = edge.from_id) "
    "MATCH (to:Paper) "
    "WHERE (to.doi IS NOT NULL AND to.doi = edge.to_id) OR (to.openalex_id = edge.to_id) "
    "MERGE (from)-[r:CITES]->(to) "
    "ON CREATE SET r.discovered_in_tier = $tier, r.run_id = $run_id, "
    "r.created_in_stage = $created_in_stage, r.created_at = datetime() "
    "WITH count(*) AS _edges_merged "
    "MATCH (source:Paper) "
    "WHERE ($source_doi IS NOT NULL AND source.doi = $source_doi) "
    "   OR ($source_openalex_id IS NOT NULL AND source.openalex_id = $source_openalex_id) "
    "MATCH (target:Paper) "
    "WHERE ($target_doi IS NOT NULL AND target.doi = $target_doi) "
    "   OR ($target_openalex_id IS NOT NULL AND target.openalex_id = $target_openalex_id) "
    "MERGE (source)-[b:BRIDGES {mechanism: $mechanism}]->(target) "
    "SET b.hop_distance = $hop_distance, "
    "    b.intermediate_nodes = [n IN $path_nodes | coalesce(n.doi, n.openalex_id)], "
    "    b.confidence = $confidence, "
    "    b.discovered_tier = $tier, "
    "    b.run_id = $run_id, "
    "    b.created_in_stage = $created_in_stage, "
    "    b.updated_at = datetime();"
)

DIRECT_BRIDGE_CYPHER = (
    "MATCH (source:Paper) "
    "WHERE ($source_doi IS NOT NULL AND source.doi = $source_doi) "
    "   OR ($source_openalex_id IS NOT NULL AND source.openalex_id = $source_openalex_id) "
    "MATCH (target:Paper) "
    "WHERE ($target_doi IS NOT NULL AND target.doi = $target_doi) "
    "   OR ($target_openalex_id IS NOT NULL AND target.openalex_id = $target_openalex_id) "
    "MERGE (source)-[b:BRIDGES {mechanism: $mechanism}]->(target) "
    "SET b.hop_distance = $hop_distance, "
    "    b.intermediate_nodes = [], "
    "    b.confidence = $confidence, "
    "    b.discovered_tier = $tier, "
    "    b.run_id = $run_id, "
    "    b.created_in_stage = $created_in_stage, "
    "    b.updated_at = datetime();"
)


def compute_adaptive_tau(similarities: list[float], tau_base: float = 0.70) -> float:
    """Compute adaptive semantic pruning threshold tau_h = max(tau_base, mu_h - 0.5 * sigma_h)."""
    if not similarities:
        return tau_base
    n = len(similarities)
    mean_sim = sum(similarities) / n
    if n == 1:
        return max(tau_base, mean_sim)
    variance = sum((x - mean_sim) ** 2 for x in similarities) / n
    std_dev = math.sqrt(variance)
    dynamic_tau = mean_sim - 0.5 * std_dev
    return max(tau_base, round(dynamic_tau, 4))


def validate_temporal_order(
    source_year: int | None,
    intermediate_year: int | None,
    target_year: int | None,
) -> bool:
    """Validate chronological causality for directed lineage: Year(A) >= Year(U) >= Year(C)."""
    if intermediate_year is None:
        return True
    if source_year is not None and intermediate_year > source_year:
        return False
    if target_year is not None and intermediate_year < target_year:
        return False
    return True


def prune_and_rank_candidates(
    candidates: list[BridgeHopCandidate],
    tau_h: float,
    max_k: int = 25,
) -> list[BridgeHopCandidate]:
    """Filter candidates below adaptive tau_h and return top Kh <= 25 ranked candidates."""
    surviving: list[BridgeHopCandidate] = []
    for cand in candidates:
        if cand.cosine_similarity >= tau_h:
            cand.is_pruned = False
            surviving.append(cand)
        else:
            cand.is_pruned = True
    surviving.sort(
        key=lambda c: (c.cosine_similarity + 0.1 * c.pagerank_score),
        reverse=True,
    )
    return surviving[:max_k]


def build_layer0_query() -> str:
    """Return parameterized Cypher query for SVPL Layer 0 local graph check."""
    return LAYER0_CYPHER


def build_materialize_pathway_query() -> str:
    """Return parameterized Cypher query for SVPL Layer 4 bridge materialization."""
    return MATERIALIZE_PATHWAY_CYPHER


def build_direct_bridge_query() -> str:
    """Return Cypher query for summary bridge edge when intermediate nodes are empty."""
    return DIRECT_BRIDGE_CYPHER


def _build_path_node_dicts(nodes: list[BridgeNodeSummary]) -> list[dict[str, Any]]:
    """Convert BridgeNodeSummary models to Cypher parameter dicts."""
    return [
        {
            "openalex_id": node.openalex_id,
            "doi": node.doi,
            "title": node.title,
            "year": node.year,
            "cited_by_count": node.cited_by_count or 0,
            "is_stub": node.is_stub,
        }
        for node in nodes
    ]


def _build_materialize_params(
    source_doi: str, target_doi: str, s_id: str | None, t_id: str | None,
    mechanism: str, hop: int, conf: float, run_id: str, stage_idx: int,
    path_nodes: list[dict[str, Any]], edges: list[dict[str, str]],
) -> dict[str, Any]:
    """Construct parameter mapping for Neo4j bridge materialization."""
    return {
        "source_doi": source_doi, "target_doi": target_doi,
        "source_openalex_id": s_id, "target_openalex_id": t_id,
        "mechanism": mechanism, "hop_distance": hop, "confidence": conf,
        "tier": 1, "run_id": run_id, "created_in_stage": stage_idx,
        "path_nodes": path_nodes, "edges": edges,
    }



def _parse_direct_path(source_doi: str, target_doi: str) -> MultiHopBridgePathway:
    """Construct MultiHopBridgePathway for Layer 0 direct connection."""
    return MultiHopBridgePathway(
        pathway_id=str(uuid.uuid4()),
        source_doi=source_doi,
        target_doi=target_doi,
        intermediate_nodes=[],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=0,
        confidence=1.0,
        hop_distance=1,
    )


def _parse_two_hop_path(
    row: dict[str, Any], source_doi: str, target_doi: str
) -> MultiHopBridgePathway:
    """Construct MultiHopBridgePathway for Layer 0 two-hop local connection."""
    summary = BridgeNodeSummary(
        openalex_id=str(row.get("intermediate_openalex_id") or "local_stub"),
        doi=row.get("intermediate_doi"),
        title=str(row.get("intermediate_title") or "Local Bridge Node"),
        year=row.get("intermediate_year"),
        cited_by_count=row.get("intermediate_cited_by_count"),
        is_stub=bool(row.get("is_stub", False)),
    )
    return MultiHopBridgePathway(
        pathway_id=str(uuid.uuid4()),
        source_doi=source_doi,
        target_doi=target_doi,
        intermediate_nodes=[summary],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=0,
        confidence=1.0,
        hop_distance=2,
    )


async def _check_primitive(
    fetcher: Any,
    mechanism: BridgeMechanism,
    source_id: str,
    target_id: str,
) -> tuple[BridgeNodeSummary, BridgeMechanism] | None:
    """Execute a single undirected relational primitive and extract top node summary."""
    works = await fetcher(source_id, target_id)
    if not works:
        return None
    best = works[0]
    summary = BridgeNodeSummary(
        openalex_id=str(best.get("openalex_id") or best.get("id")),
        doi=best.get("doi"),
        title=str(best.get("title") or f"{mechanism.value} Bridge Work"),
        year=best.get("year"),
        cited_by_count=best.get("cited_by_count"),
    )
    return summary, mechanism


def _build_layer2_nodes(
    refs: list[str], top_result: dict[str, Any]
) -> list[BridgeNodeSummary]:
    """Construct intermediate node summaries for Layer 2 disjunctive 3-hop pathway."""
    u1 = BridgeNodeSummary(openalex_id=refs[0], title=f"Disjunctive Hop 1 ({refs[0]})", is_stub=True)
    u2 = BridgeNodeSummary(
        openalex_id=str(top_result.get("openalex_id") or top_result.get("id")),
        doi=top_result.get("doi"),
        title=str(top_result.get("title") or "Disjunctive Hop 2 Bridge"),
        year=top_result.get("year"),
        cited_by_count=top_result.get("cited_by_count"),
    )
    return [u1, u2]


class SVPLService:
    """Scientometric-Vector Progressive Ladder multi-hop traversal orchestrator."""

    def __init__(
        self,
        neo4j_service: Neo4jService | None = None,
        openalex_service: OpenAlexService | None = None,
    ) -> None:
        self._neo4j = neo4j_service
        self._openalex = openalex_service

    async def execute_layer0(
        self,
        source_doi: str,
        target_doi: str,
    ) -> MultiHopBridgePathway | None:
        """Layer 0: Query local Neo4j graph for direct or 2-hop path (<10ms, 0 API calls)."""
        if self._neo4j is None:
            return None
        rows = await self._neo4j.execute_read(
            build_layer0_query(),
            {"source_doi": source_doi, "target_doi": target_doi},
        )
        if not rows:
            return None
        return self._parse_layer0_result(rows[0], source_doi, target_doi)

    def _parse_layer0_result(
        self,
        row: dict[str, Any],
        source_doi: str,
        target_doi: str,
    ) -> MultiHopBridgePathway | None:
        """Parse local Cypher record into MultiHopBridgePathway."""
        conn_type = row.get("connection_type")
        if conn_type == "direct":
            return _parse_direct_path(source_doi, target_doi)
        if conn_type == "two_hop":
            return _parse_two_hop_path(row, source_doi, target_doi)
        return None

    async def _evaluate_directed_primitive(
        self,
        source_id: str,
        target_id: str,
        source_year: int | None,
        target_year: int | None,
    ) -> tuple[BridgeNodeSummary, BridgeMechanism] | None:
        """Evaluate directed 2-hop with chronological ordering."""
        if self._openalex is None:
            return None
        works = await self._openalex.find_2hop_directed(source_id, target_id)
        for w in works:
            w_year = w.get("year")
            if validate_temporal_order(source_year, w_year, target_year):
                summary = BridgeNodeSummary(
                    openalex_id=str(w.get("openalex_id") or w.get("id")),
                    doi=w.get("doi"),
                    title=str(w.get("title") or "Directed Bridge Work"),
                    year=w_year,
                    cited_by_count=w.get("cited_by_count"),
                )
                return summary, BridgeMechanism.DIRECTED_2HOP
        return None

    async def _evaluate_undirected_primitives(
        self,
        source_id: str,
        target_id: str,
    ) -> tuple[BridgeNodeSummary, BridgeMechanism] | None:
        """Evaluate reverse directed, coupling, and co-citation relational primitives."""
        if self._openalex is None:
            return None
        checks: list[tuple[Any, BridgeMechanism]] = [
            (self._openalex.find_2hop_reverse, BridgeMechanism.REVERSE_DIRECTED_2HOP),
            (self._openalex.find_bibliographic_coupling, BridgeMechanism.BIBLIOGRAPHIC_COUPLING),
            (self._openalex.find_co_citation, BridgeMechanism.CO_CITATION),
        ]
        for fetcher, mechanism in checks:
            res = await _check_primitive(fetcher, mechanism, source_id, target_id)
            if res is not None:
                return res
        return None

    async def _materialize_layer1(
        self,
        source_doi: str,
        target_doi: str,
        summary: BridgeNodeSummary,
        mechanism: BridgeMechanism,
        run_id: str,
        stage_index: int,
    ) -> MultiHopBridgePathway:
        """Persist and construct MultiHopBridgePathway for Layer 1 discovery."""
        conf = 0.95 if mechanism == BridgeMechanism.DIRECTED_2HOP else 0.88
        await self.materialize_bridge_pathway(
            source_doi=source_doi, target_doi=target_doi, mechanism=mechanism,
            hop_distance=2, confidence=conf, intermediate_nodes=[summary],
            run_id=run_id, stage_index=stage_index,
        )
        return MultiHopBridgePathway(
            pathway_id=str(uuid.uuid4()), source_doi=source_doi, target_doi=target_doi,
            intermediate_nodes=[summary], mechanism=mechanism, discovered_layer=1,
            confidence=conf, hop_distance=2,
        )

    async def execute_layer1(
        self,
        source_doi: str,
        target_doi: str,
        source_year: int | None = None,
        target_year: int | None = None,
        run_id: str = "run_default",
        stage_index: int = 2,
    ) -> MultiHopBridgePathway | None:
        """Layer 1: Execute 1-shot server-side relational primitives in single GET requests."""
        if self._openalex is None:
            return None
        res = await self._evaluate_directed_primitive(source_doi, target_doi, source_year, target_year)
        if res is None:
            res = await self._evaluate_undirected_primitives(source_doi, target_doi)
        if res is None:
            return None
        summary, mechanism = res
        return await self._materialize_layer1(
            source_doi, target_doi, summary, mechanism, run_id, stage_index
        )

    async def _materialize_layer2(
        self,
        source_doi: str,
        target_doi: str,
        intermediates: list[BridgeNodeSummary],
        run_id: str,
        stage_index: int,
    ) -> MultiHopBridgePathway:
        """Persist and construct MultiHopBridgePathway for Layer 2 discovery."""
        conf = 0.82
        await self.materialize_bridge_pathway(
            source_doi=source_doi, target_doi=target_doi,
            mechanism=BridgeMechanism.PIPE_DISJUNCTIVE_3HOP,
            hop_distance=3, confidence=conf, intermediate_nodes=intermediates,
            run_id=run_id, stage_index=stage_index,
        )
        return MultiHopBridgePathway(
            pathway_id=str(uuid.uuid4()), source_doi=source_doi, target_doi=target_doi,
            intermediate_nodes=intermediates, mechanism=BridgeMechanism.PIPE_DISJUNCTIVE_3HOP,
            discovered_layer=2, confidence=conf, hop_distance=3,
        )

    async def execute_layer2(
        self,
        source_doi: str,
        target_doi: str,
        run_id: str = "run_default",
        stage_index: int = 2,
    ) -> MultiHopBridgePathway | None:
        """Layer 2: Pipe-disjunctive meet-in-the-middle 3-hop batching (<=50 references)."""
        if self._openalex is None:
            return None
        refs = await self._openalex.fetch_work_references(source_doi)
        if not refs:
            return None
        results = await self._openalex.batch_pipe_disjunctive_3hop(refs, target_doi)
        if not results:
            return None
        intermediates = _build_layer2_nodes(refs, results[0])
        return await self._materialize_layer2(
            source_doi, target_doi, intermediates, run_id, stage_index
        )

    async def _materialize_layer3(
        self,
        source_doi: str,
        target_doi: str,
        best: BridgeHopCandidate,
        run_id: str,
        stage_index: int,
    ) -> MultiHopBridgePathway:
        """Persist and construct MultiHopBridgePathway for Layer 3 discovery."""
        summary = BridgeNodeSummary(
            openalex_id=best.openalex_id, doi=best.doi, title=best.title, year=best.year,
        )
        conf = round(max(0.70, best.cosine_similarity), 3)
        intermediates = [summary]
        await self.materialize_bridge_pathway(
            source_doi=source_doi, target_doi=target_doi,
            mechanism=BridgeMechanism.STEINER_BEAM_3HOP,
            hop_distance=3, confidence=conf, intermediate_nodes=intermediates,
            run_id=run_id, stage_index=stage_index,
        )
        return MultiHopBridgePathway(
            pathway_id=str(uuid.uuid4()), source_doi=source_doi, target_doi=target_doi,
            intermediate_nodes=intermediates, mechanism=BridgeMechanism.STEINER_BEAM_3HOP,
            discovered_layer=3, confidence=conf, hop_distance=3,
        )

    async def execute_layer3(
        self,
        source_doi: str,
        target_doi: str,
        candidate_pool: list[BridgeHopCandidate] | None = None,
        run_id: str = "run_default",
        stage_index: int = 2,
    ) -> MultiHopBridgePathway | None:
        """Layer 3: Concept-guided Steiner Beam A* with adaptive tau pruning and Kh <= 25."""
        if not candidate_pool:
            return None
        similarities = [c.cosine_similarity for c in candidate_pool]
        tau_h = compute_adaptive_tau(similarities, tau_base=0.70)
        ranked = prune_and_rank_candidates(candidate_pool, tau_h=tau_h, max_k=25)
        if not ranked:
            return None
        return await self._materialize_layer3(
            source_doi, target_doi, ranked[0], run_id, stage_index
        )

    async def materialize_bridge_pathway(
        self, source_doi: str, target_doi: str, mechanism: BridgeMechanism,
        hop_distance: int, confidence: float, intermediate_nodes: list[BridgeNodeSummary],
        run_id: str, stage_index: int, source_openalex_id: str | None = None,
        target_openalex_id: str | None = None,
    ) -> None:
        """Layer 4: Atomic Neo4j Cypher bridge materialization merging nodes and typed edges."""
        if self._neo4j is None:
            return
        p_nodes = _build_path_node_dicts(intermediate_nodes)
        edges = self._build_pathway_edges(source_doi, target_doi, intermediate_nodes)
        params = _build_materialize_params(
            source_doi, target_doi, source_openalex_id, target_openalex_id,
            mechanism.value, hop_distance, confidence, run_id, stage_index, p_nodes, edges,
        )
        query = build_materialize_pathway_query() if p_nodes else build_direct_bridge_query()
        await self._neo4j.execute_write(query, params)

    def _build_pathway_edges(
        self,
        source_doi: str,
        target_doi: str,
        intermediates: list[BridgeNodeSummary],
    ) -> list[dict[str, str]]:
        """Construct sequential from/to edge list along the pathway."""
        if not intermediates:
            return [{"from_id": source_doi, "to_id": target_doi}]
        chain = [source_doi] + [
            node.doi or node.openalex_id for node in intermediates
        ] + [target_doi]
        return [
            {"from_id": chain[i], "to_id": chain[i + 1]}
            for i in range(len(chain) - 1)
        ]

    async def _try_shallow_layers(
        self,
        source_doi: str,
        target_doi: str,
        source_year: int | None,
        target_year: int | None,
        run_id: str,
        stage_index: int,
    ) -> MultiHopBridgePathway | None:
        """Attempt Layer 0 and Layer 1 resolution."""
        pathway = await self.execute_layer0(source_doi, target_doi)
        if pathway is not None:
            return pathway
        return await self.execute_layer1(
            source_doi, target_doi, source_year, target_year, run_id, stage_index
        )

    async def _try_deep_layers(
        self,
        source_doi: str,
        target_doi: str,
        candidate_pool: list[BridgeHopCandidate] | None,
        run_id: str,
        stage_index: int,
    ) -> MultiHopBridgePathway | None:
        """Attempt Layer 2 and Layer 3 resolution."""
        pathway = await self.execute_layer2(source_doi, target_doi, run_id, stage_index)
        if pathway is not None:
            return pathway
        return await self.execute_layer3(
            source_doi, target_doi, candidate_pool, run_id, stage_index
        )

    async def find_bridge_pathway(
        self, source_doi: str, target_doi: str, project_id: str | None = None,
        trigger_reason: Union[MultiHopAuthorization, MultiHopTriggerReason, str] = (
            MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE
        ),
        max_hops: int = 3, run_id: str | None = None, stage_index: int = 2,
        candidate_count: int = 0, source_year: int | None = None,
        target_year: int | None = None, candidate_pool: list[BridgeHopCandidate] | None = None,
    ) -> MultiHopBridgePathway | None:
        """Execute 4-layer SVPL cascade under strict necessity gating."""
        check_multihop_authorization(trigger_reason, candidate_count=candidate_count)
        act_run = run_id or str(uuid.uuid4())
        shallow = await self._try_shallow_layers(
            source_doi, target_doi, source_year, target_year, act_run, stage_index
        )
        if shallow is not None or max_hops < 3:
            return shallow
        return await self._try_deep_layers(
            source_doi, target_doi, candidate_pool, act_run, stage_index
        )

