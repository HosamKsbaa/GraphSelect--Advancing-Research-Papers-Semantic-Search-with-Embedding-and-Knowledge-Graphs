"""Comprehensive test suite for SVPL Multi-Hop Bridge Traversal (US3 / R2).

Verifies:
- Strict Necessity Gating (FR-015): MultiHopUnauthorizedError (HTTP 403) on unauthorized triggers.
- Gating edge cases: routine crawler blocked, empty gap with N>0 blocked, valid triggers allowed.
- OpenAlex 1-shot server-side relational primitives:
  - Directed 2-hop (cited_by:A, cites:C)
  - Reverse directed 2-hop (cites:A, cited_by:C)
  - Bibliographic coupling (cited_by:A, cited_by:C)
  - Co-citation convergence (cites:A, cites:C)
  - Layer 2 pipe-disjunctive 3-hop batching (k <= 50) and reference fetching.
- SVPL 4-Layer Cascade:
  - Layer 0: Local Neo4j in-graph stub check (<10ms, 0 network calls).
  - Layer 1: Server-side relational primitives cascade with temporal causality.
  - Layer 2: Pipe-disjunctive meet-in-the-middle batching.
  - Layer 3: Concept-guided Steiner Beam A* with adaptive tau_h pruning and Kh <= 25.
  - Layer 4: Atomic Neo4j Cypher bridge materialization (merging on DOI, fallback OpenAlex ID).
"""
from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.errors.enhancement_errors import MultiHopUnauthorizedError
from features.ranking.svpl_gating import (
    check_multihop_authorization,
    is_multihop_authorized,
    parse_trigger_reason,
    validate_gap_remediation_candidate_count,
)
from features.ranking.svpl_models import (
    BridgeHopCandidate,
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopAuthorization,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
)
from features.ranking.svpl_service import (
    SVPLService,
    build_direct_bridge_query,
    build_layer0_query,
    build_materialize_pathway_query,
    compute_adaptive_tau,
    prune_and_rank_candidates,
    validate_temporal_order,
)


# ==============================================================================
# 1. Strict Necessity Gating Tests (FR-015)
# ==============================================================================

def test_gating_blocks_routine_crawler() -> None:
    """Routine crawler or unapproved triggers must raise MultiHopUnauthorizedError (HTTP 403)."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        check_multihop_authorization("routine_crawler")
    assert exc_info.value.http_status_code == 403
    assert "MULTIHOP_UNAUTHORIZED" in str(exc_info.value)


def test_gating_blocks_general_discovery() -> None:
    """General discovery or snowballing triggers must be rejected."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        check_multihop_authorization("snowballing")
    assert exc_info.value.http_status_code == 403


def test_gating_blocks_unauthorized_payload() -> None:
    """MultiHopAuthorization with is_authorized=False must be rejected."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
        requester="UserSession_1",
        context_description="Investigating relation between paper A and paper B",
        is_authorized=False,
    )
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        check_multihop_authorization(auth)
    assert exc_info.value.http_status_code == 403


def test_gating_blocks_gap_remediation_when_n_greater_zero() -> None:
    """Gap remediation may only invoke multi-hop when candidates are exhausted (N=0)."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        requester="GapRemediationAgent",
        context_description="Literature deficit in active RQ",
        is_authorized=True,
    )
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        check_multihop_authorization(auth, candidate_count=3)
    assert exc_info.value.http_status_code == 403
    assert "N=0" in str(exc_info.value)


def test_gating_allows_explicit_user_directive() -> None:
    """Explicit user directive passes gating check cleanly."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
        requester="Researcher",
        context_description="Explain lineage between paper A and paper B",
        is_authorized=True,
    )
    check_multihop_authorization(auth)
    assert is_multihop_authorized(auth) is True


def test_gating_allows_empty_gap_remediation_when_n_zero() -> None:
    """Empty gap remediation with candidate_count=0 passes gating check."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        requester="GapRemediationAgent",
        context_description="No candidates found in Stage 2 snowballing",
        is_authorized=True,
    )
    check_multihop_authorization(auth, candidate_count=0)
    assert is_multihop_authorized(auth, candidate_count=0) is True


def test_is_multihop_authorized_helper() -> None:
    """Helper returns True/False predicates without throwing exceptions."""
    assert is_multihop_authorized(MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE) is True
    assert is_multihop_authorized("explicit_user_directive") is True
    assert is_multihop_authorized("empty_gap_remediation", candidate_count=0) is True
    assert is_multihop_authorized("empty_gap_remediation", candidate_count=2) is False
    assert is_multihop_authorized("invalid_trigger") is False


# ==============================================================================
# 2. SVPL Layer 0: Local In-Graph & Stub Check Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_layer0_direct_path_hit() -> None:
    """Layer 0 returns immediate 1-hop path when direct edge exists in local graph."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "direct"}]
    service = SVPLService(neo4j_service=mock_neo4j)

    res = await service.execute_layer0("10.1145/source", "10.1145/target")
    assert res is not None
    assert res.discovered_layer == 0
    assert res.hop_distance == 1
    assert res.mechanism == BridgeMechanism.DIRECTED_2HOP
    assert res.confidence == 1.0
    assert len(res.intermediate_nodes) == 0


@pytest.mark.asyncio
async def test_layer0_two_hop_path_hit() -> None:
    """Layer 0 returns 2-hop path when intermediate paper exists in local graph."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [
        {
            "connection_type": "two_hop",
            "intermediate_doi": "10.1145/bridge_mid",
            "intermediate_openalex_id": "W9999",
            "intermediate_title": "Local Bridge Node",
            "intermediate_year": 2023,
            "intermediate_cited_by_count": 55,
            "is_stub": True,
        }
    ]
    service = SVPLService(neo4j_service=mock_neo4j)

    res = await service.execute_layer0("10.1145/source", "10.1145/target")
    assert res is not None
    assert res.discovered_layer == 0
    assert res.hop_distance == 2
    assert len(res.intermediate_nodes) == 1
    assert res.intermediate_nodes[0].doi == "10.1145/bridge_mid"
    assert res.intermediate_nodes[0].is_stub is True


@pytest.mark.asyncio
async def test_layer0_miss_returns_none() -> None:
    """Layer 0 returns None when no direct or 2-hop local connection exists."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "none"}]
    service = SVPLService(neo4j_service=mock_neo4j)

    res = await service.execute_layer0("10.1145/source", "10.1145/target")
    assert res is None


# ==============================================================================
# 3. OpenAlex 1-Shot Relational Primitives & Batching Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_openalex_find_2hop_directed() -> None:
    """find_2hop_directed calls OpenAlex with cited_by:A,cites:C filter."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    mock_data = {
        "results": [
            {
                "id": "https://openalex.org/W1234",
                "doi": "https://doi.org/10.1145/bridge1",
                "title": "Intermediate Work",
                "publication_year": 2022,
                "cited_by_count": 40,
            }
        ]
    }
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)) as mock_req:
        res = await service.find_2hop_directed("10.1145/source", "10.1145/target")
        assert len(res) == 1
        assert res[0]["doi"] == "10.1145/bridge1"
        assert res[0]["year"] == 2022
        mock_req.assert_called_once()
        params = mock_req.call_args[1]["params"]
        assert params["filter"] == "cited_by:doi:10.1145/source,cites:doi:10.1145/target"


@pytest.mark.asyncio
async def test_openalex_find_2hop_reverse() -> None:
    """find_2hop_reverse calls OpenAlex with cites:A,cited_by:C filter."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    mock_data = {"results": [{"id": "W2222", "title": "Reverse Work", "publication_year": 2021}]}
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)) as mock_req:
        res = await service.find_2hop_reverse("W1111", "W3333")
        assert len(res) == 1
        params = mock_req.call_args[1]["params"]
        assert params["filter"] == "cites:W1111,cited_by:W3333"


@pytest.mark.asyncio
async def test_openalex_bibliographic_coupling() -> None:
    """find_bibliographic_coupling calls cited_by:A,cited_by:C."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    mock_data = {"results": [{"id": "W4444", "title": "Coupled Ancestor", "publication_year": 2018}]}
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)) as mock_req:
        res = await service.find_bibliographic_coupling("W1111", "W3333")
        assert len(res) == 1
        params = mock_req.call_args[1]["params"]
        assert params["filter"] == "cited_by:W1111,cited_by:W3333"


@pytest.mark.asyncio
async def test_openalex_co_citation() -> None:
    """find_co_citation calls cites:A,cites:C."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    mock_data = {"results": [{"id": "W5555", "title": "Co-Citing Paper", "publication_year": 2024}]}
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)) as mock_req:
        res = await service.find_co_citation("W1111", "W3333")
        assert len(res) == 1
        params = mock_req.call_args[1]["params"]
        assert params["filter"] == "cites:W1111,cites:W3333"


@pytest.mark.asyncio
async def test_openalex_batch_pipe_disjunctive_3hop_chunking() -> None:
    """batch_pipe_disjunctive_3hop chunks references into batches of <=50."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    refs = [f"W{i}" for i in range(75)]
    mock_data = {"results": [{"id": "W999", "title": "3Hop Target"}]}
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)) as mock_req:
        res = await service.batch_pipe_disjunctive_3hop(refs, "WTarget")
        assert mock_req.call_count == 2
        assert len(res) == 2


@pytest.mark.asyncio
async def test_openalex_fetch_work_references() -> None:
    """fetch_work_references extracts clean reference identifiers."""
    from core.clients.openalex_client import OpenAlexService
    service = OpenAlexService(api_key="")
    mock_data = {"referenced_works": ["https://openalex.org/W101", "https://openalex.org/W102"]}
    with patch.object(service, "_request", new=AsyncMock(return_value=mock_data)):
        refs = await service.fetch_work_references("W100")
        assert refs == ["W101", "W102"]


# ==============================================================================
# 4. Temporal Order Validation & Causality
# ==============================================================================

def test_temporal_order_valid() -> None:
    """Strict chronological order Year(A) >= Year(U) >= Year(C) passes."""
    assert validate_temporal_order(2024, 2022, 2020) is True
    assert validate_temporal_order(2024, 2024, 2024) is True
    assert validate_temporal_order(None, 2022, None) is True


def test_temporal_order_paradox_future_intermediate() -> None:
    """Intermediate paper published after source paper fails temporal check."""
    assert validate_temporal_order(2020, 2024, 2018) is False


def test_temporal_order_paradox_intermediate_before_target() -> None:
    """Intermediate paper published before target paper fails when citing target."""
    assert validate_temporal_order(2024, 2018, 2020) is False


# ==============================================================================
# 5. SVPL Layer 1 & Layer 2 Service Execution Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_svpl_layer1_directed_success() -> None:
    """Layer 1 resolves directed 2-hop and materializes pathway."""
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = [
        {"openalex_id": "W123", "doi": "10.1145/u", "title": "U", "year": 2022, "cited_by_count": 20}
    ]
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    path = await service.execute_layer1("10.1145/a", "10.1145/c", source_year=2024, target_year=2020)
    assert path is not None
    assert path.discovered_layer == 1
    assert path.mechanism == BridgeMechanism.DIRECTED_2HOP
    assert path.confidence == 0.95
    assert len(path.intermediate_nodes) == 1
    mock_neo4j.execute_write.assert_called_once()


@pytest.mark.asyncio
async def test_svpl_layer1_skips_temporal_paradox() -> None:
    """Layer 1 skips intermediate candidates violating chronological causality."""
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = [
        {"openalex_id": "W_future", "year": 2025}
    ]
    mock_openalex.find_2hop_reverse.return_value = []
    mock_openalex.find_bibliographic_coupling.return_value = []
    mock_openalex.find_co_citation.return_value = []
    service = SVPLService(openalex_service=mock_openalex)

    path = await service.execute_layer1("10.1145/a", "10.1145/c", source_year=2024, target_year=2020)
    assert path is None


@pytest.mark.asyncio
async def test_svpl_layer1_fallback_to_coupling() -> None:
    """Layer 1 falls back to bibliographic coupling when directed yields no candidates."""
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = []
    mock_openalex.find_2hop_reverse.return_value = []
    mock_openalex.find_bibliographic_coupling.return_value = [
        {"openalex_id": "W_shared", "title": "Foundational Ancestor", "year": 2018}
    ]
    service = SVPLService(openalex_service=mock_openalex)

    path = await service.execute_layer1("10.1145/a", "10.1145/c")
    assert path is not None
    assert path.mechanism == BridgeMechanism.BIBLIOGRAPHIC_COUPLING
    assert path.discovered_layer == 1


@pytest.mark.asyncio
async def test_svpl_layer2_pipe_disjunctive_hit() -> None:
    """Layer 2 resolves 3-hop bridge via pipe-disjunctive batching."""
    mock_openalex = AsyncMock()
    mock_openalex.fetch_work_references.return_value = ["W_ref1", "W_ref2"]
    mock_openalex.batch_pipe_disjunctive_3hop.return_value = [
        {"openalex_id": "W_mid2", "doi": "10.1145/mid2", "title": "Hop 2 Paper", "year": 2022}
    ]
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    path = await service.execute_layer2("10.1145/a", "10.1145/c")
    assert path is not None
    assert path.discovered_layer == 2
    assert path.mechanism == BridgeMechanism.PIPE_DISJUNCTIVE_3HOP
    assert path.hop_distance == 3
    assert len(path.intermediate_nodes) == 2
    mock_neo4j.execute_write.assert_called_once()


# ==============================================================================
# 6. SVPL Layer 3: Adaptive Tau Pruning & Steiner Beam Search Tests
# ==============================================================================

def test_compute_adaptive_tau_empty() -> None:
    """Empty similarity list defaults to base tau = 0.70."""
    assert compute_adaptive_tau([]) == 0.70


def test_compute_adaptive_tau_single_element() -> None:
    """Single element returns max(tau_base, score)."""
    assert compute_adaptive_tau([0.85]) == 0.85
    assert compute_adaptive_tau([0.65]) == 0.70


def test_compute_adaptive_tau_distribution() -> None:
    """Multi-element list computes mean - 0.5 * std_dev bounded by tau_base."""
    sims = [0.85, 0.80, 0.75, 0.60]
    tau = compute_adaptive_tau(sims, tau_base=0.70)
    assert tau >= 0.70
    assert tau == pytest.approx(0.7032, abs=1e-3)


def test_prune_and_rank_candidates() -> None:
    """Pruning removes candidates below tau_h and caps at Kh <= 25."""
    candidates = [
        BridgeHopCandidate(
            openalex_id=f"W{i}",
            title=f"Paper {i}",
            hop_level=1,
            cosine_similarity=0.60 + (i * 0.01),
            adaptive_threshold_tau=0.70,
        )
        for i in range(35)
    ]
    surviving = prune_and_rank_candidates(candidates, tau_h=0.70, max_k=25)
    assert len(surviving) == 25
    assert all(c.cosine_similarity >= 0.70 for c in surviving)
    assert all(c.is_pruned is False for c in surviving)


@pytest.mark.asyncio
async def test_svpl_layer3_steiner_beam_execution() -> None:
    """Layer 3 executes concept-guided Steiner Beam with surviving candidates."""
    candidates = [
        BridgeHopCandidate(
            openalex_id="W_steiner",
            title="Steiner Concept Bridge",
            hop_level=2,
            cosine_similarity=0.78,
            adaptive_threshold_tau=0.70,
        )
    ]
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j)

    path = await service.execute_layer3("10.1145/a", "10.1145/c", candidate_pool=candidates)
    assert path is not None
    assert path.discovered_layer == 3
    assert path.mechanism == BridgeMechanism.STEINER_BEAM_3HOP
    assert path.confidence == 0.78
    mock_neo4j.execute_write.assert_called_once()


# ==============================================================================
# 7. SVPL Layer 4: Materialization & Cypher Query Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_materialize_bridge_pathway_cypher_call() -> None:
    """Layer 4 sends valid Cypher query and parameters to Neo4j execute_write."""
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j)
    node = BridgeNodeSummary(openalex_id="W123", doi="10.1145/bridge_paper", title="P", year=2023)
    await service.materialize_bridge_pathway(
        source_doi="10.1145/src", target_doi="10.1145/tgt",
        mechanism=BridgeMechanism.DIRECTED_2HOP, hop_distance=2,
        confidence=0.95, intermediate_nodes=[node], run_id="run_123", stage_index=2,
    )
    mock_neo4j.execute_write.assert_called_once()
    query, params = mock_neo4j.execute_write.call_args[0][:2]
    assert "MERGE (source)-[b:BRIDGES" in query
    assert params["source_doi"] == "10.1145/src"
    assert params["target_doi"] == "10.1145/tgt"
    assert params["mechanism"] == "directed_2hop"
    assert params["run_id"] == "run_123"



# ==============================================================================
# 8. Full Cascade End-to-End Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_full_cascade_layer0_hit() -> None:
    """When Layer 0 hits, OpenAlex is never called."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "direct"}]
    mock_openalex = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    res = await service.find_bridge_pathway(
        "10.1145/src",
        "10.1145/tgt",
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
    )
    assert res is not None
    assert res.discovered_layer == 0
    mock_openalex.find_2hop_directed.assert_not_called()


@pytest.mark.asyncio
async def test_full_cascade_layer1_hit() -> None:
    """When Layer 0 misses and Layer 1 hits, Layer 2 & 3 are not invoked."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "none"}]
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = [
        {"openalex_id": "W1", "doi": "10.1145/u1", "title": "U1", "year": 2022}
    ]
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    res = await service.find_bridge_pathway(
        "10.1145/src",
        "10.1145/tgt",
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
    )
    assert res is not None
    assert res.discovered_layer == 1
    mock_openalex.fetch_work_references.assert_not_called()


@pytest.mark.asyncio
async def test_full_cascade_exhausted_returns_none() -> None:
    """When all layers return empty, find_bridge_pathway cleanly returns None."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "none"}]
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = []
    mock_openalex.find_2hop_reverse.return_value = []
    mock_openalex.find_bibliographic_coupling.return_value = []
    mock_openalex.find_co_citation.return_value = []
    mock_openalex.fetch_work_references.return_value = []
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    res = await service.find_bridge_pathway(
        "10.1145/src",
        "10.1145/tgt",
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
    )
    assert res is None
