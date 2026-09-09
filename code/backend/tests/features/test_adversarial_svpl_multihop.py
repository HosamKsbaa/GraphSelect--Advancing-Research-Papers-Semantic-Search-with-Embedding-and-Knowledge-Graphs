"""Adversarial Stress Test Suite for Milestone M3 SVPL Multi-Hop Traversal (US3 / R2).

Empirically tests edge cases, boundary conditions, malicious payloads,
and theoretical paradoxes against:
1. Gating invariants (FR-015): Unauthorized strings, malformed types, 0-call guarantee.
2. Gap remediation trigger boundaries: N=0 vs N>0 vs N<0, non-integer inputs.
3. Temporal causality paradoxes: Forward/backward time violations, missing years, reverse directed.
4. Layer 3 adaptive pruning: Extreme similarity distributions, zero variance, Kh <= 25 cap.
5. Search depth controls: max_hops boundary enforcement and cascade exhaustion.
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
    compute_adaptive_tau,
    prune_and_rank_candidates,
    validate_temporal_order,
)


# ==============================================================================
# 1. Adversarial Gating & Security Stress Tests (FR-015)
# ==============================================================================

def test_adv_gating_rejects_empty_and_whitespace_triggers() -> None:
    """Empty and whitespace strings must be rejected with HTTP 403."""
    for payload in ["", "   ", "\t\n\r", "   \n"]:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(payload)
        assert exc.value.http_status_code == 403
        assert is_multihop_authorized(payload) is False


def test_adv_gating_rejects_sql_and_cypher_injection_payloads() -> None:
    """Injection vectors must be safely rejected by gating with HTTP 403."""
    payloads = [
        "'; DROP TABLE papers; --",
        "' OR 1=1 --",
        "MATCH (n) DETACH DELETE n RETURN n",
        "admin'--",
        "explicit_user_directive'; DROP TABLE --",
    ]
    for payload in payloads:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(payload)
        assert exc.value.http_status_code == 403
        assert is_multihop_authorized(payload) is False


def test_adv_gating_rejects_malformed_types() -> None:
    """Non-string/non-model payloads must be rejected with HTTP 403."""
    bad_payloads: list[Any] = [123, 0, False, None, [1, 2], {"trigger": "user"}, 3.14]
    for bad in bad_payloads:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(bad)
        assert exc.value.http_status_code == 403
        assert is_multihop_authorized(bad) is False


def test_adv_gating_rejects_unauthorized_token_revocation() -> None:
    """MultiHopAuthorization with is_authorized=False must be strictly rejected."""
    auth = MultiHopAuthorization(
        trigger_reason=MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
        requester="RevokedAgent",
        context_description="Security token revoked mid-execution",
        is_authorized=False,
    )
    with pytest.raises(MultiHopUnauthorizedError) as exc:
        check_multihop_authorization(auth)
    assert exc.value.http_status_code == 403
    assert is_multihop_authorized(auth) is False


@pytest.mark.asyncio
async def test_adv_gating_guarantees_zero_external_calls_on_rejection() -> None:
    """Unauthorized triggers must execute ZERO Neo4j and ZERO OpenAlex calls."""
    mock_neo4j = AsyncMock()
    mock_openalex = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    for bad in ["routine_crawler", "snowballing", "admin", ""]:
        with pytest.raises(MultiHopUnauthorizedError):
            await service.find_bridge_pathway("10.1/a", "10.1/b", trigger_reason=bad)

    assert mock_neo4j.execute_read.call_count == 0
    assert mock_neo4j.execute_write.call_count == 0
    assert mock_openalex.find_2hop_directed.call_count == 0


# ==============================================================================
# 2. Gap Remediation Candidate Count Boundaries (FR-015)
# ==============================================================================

def test_adv_gating_gap_remediation_n_zero_allowed() -> None:
    """Candidate count N=0 must pass gating for empty_gap_remediation."""
    reason = MultiHopTriggerReason.EMPTY_GAP_REMEDIATION
    check_multihop_authorization(reason, candidate_count=0)
    assert is_multihop_authorized(reason, candidate_count=0) is True


def test_adv_gating_gap_remediation_positive_n_rejected() -> None:
    """Candidate count N=1, 2, 10 must be rejected with HTTP 403."""
    reason = MultiHopTriggerReason.EMPTY_GAP_REMEDIATION
    for count in [1, 2, 10, 500]:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(reason, candidate_count=count)
        assert exc.value.http_status_code == 403
        assert is_multihop_authorized(reason, candidate_count=count) is False


def test_adv_gating_gap_remediation_non_integer_rejected() -> None:
    """Non-integer candidate counts (e.g. 0.5, inf) must be blocked."""
    reason = MultiHopTriggerReason.EMPTY_GAP_REMEDIATION
    for val in [0.5, 1.5, float("inf")]:
        with pytest.raises(MultiHopUnauthorizedError) as exc:
            check_multihop_authorization(reason, candidate_count=val)  # type: ignore[arg-type]
        assert exc.value.http_status_code == 403


@pytest.mark.asyncio
async def test_adv_gating_gap_remediation_zero_calls_on_positive_n() -> None:
    """Non-empty gap remediation attempts must make 0 external calls."""
    mock_neo4j = AsyncMock()
    mock_openalex = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    with pytest.raises(MultiHopUnauthorizedError):
        await service.find_bridge_pathway(
            "10.1/a", "10.1/b",
            trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
            candidate_count=5,
        )

    assert mock_neo4j.execute_read.call_count == 0
    assert mock_openalex.find_2hop_directed.call_count == 0


# ==============================================================================
# 3. Temporal Paradox & Chronological Causality Attacks
# ==============================================================================

def test_adv_temporal_causality_strict_monotonic_chain() -> None:
    """Standard monotonic citation lineage 2024 -> 2022 -> 2020 must pass."""
    assert validate_temporal_order(2024, 2022, 2020) is True
    assert validate_temporal_order(2024, 2024, 2020) is True
    assert validate_temporal_order(2024, 2020, 2020) is True


def test_adv_temporal_paradox_future_intermediate_rejected() -> None:
    """Intermediate published after source paper violates causality."""
    assert validate_temporal_order(2020, 2024, 2018) is False
    assert validate_temporal_order(2020, 2021, 2010) is False


def test_adv_temporal_paradox_intermediate_older_than_target_rejected() -> None:
    """Intermediate published before target paper cannot cite target."""
    assert validate_temporal_order(2024, 2018, 2020) is False
    assert validate_temporal_order(2024, 1999, 2000) is False


def test_adv_temporal_same_year_boundary() -> None:
    """Papers published in the same calendar year are causally permissible."""
    assert validate_temporal_order(2023, 2023, 2023) is True


def test_adv_temporal_missing_endpoint_years_handled() -> None:
    """Missing source or target publication years default safely."""
    assert validate_temporal_order(None, 2022, 2020) is True
    assert validate_temporal_order(2024, 2022, None) is True
    assert validate_temporal_order(None, 2022, None) is True


@pytest.mark.asyncio
async def test_adv_layer1_prunes_temporal_paradox_candidates() -> None:
    """Layer 1 skips intermediate candidates violating chronological causality."""
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = [
        {"openalex_id": "W_future", "title": "Future Bridge", "year": 2025},
        {"openalex_id": "W_past", "title": "Too Old Bridge", "year": 2010},
        {"openalex_id": "W_valid", "title": "Valid Bridge", "year": 2022},
    ]
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)

    path = await service.execute_layer1("10.1/a", "10.1/c", source_year=2024, target_year=2020)
    assert path is not None
    assert len(path.intermediate_nodes) == 1
    assert path.intermediate_nodes[0].openalex_id == "W_valid"
    assert path.intermediate_nodes[0].year == 2022


# ==============================================================================
# 4. Adaptive Semantic Pruning & Extreme Similarity Distributions
# ==============================================================================

def test_adv_adaptive_tau_empty_pool() -> None:
    """Empty similarity pool defaults strictly to base threshold 0.70."""
    assert compute_adaptive_tau([]) == 0.70


def test_adv_adaptive_tau_single_above_and_below_base() -> None:
    """Single candidate pool returns max(0.70, score)."""
    assert compute_adaptive_tau([0.92]) == 0.92
    assert compute_adaptive_tau([0.75]) == 0.75
    assert compute_adaptive_tau([0.55]) == 0.70
    assert compute_adaptive_tau([0.0]) == 0.70


def test_adv_adaptive_tau_zero_variance_high_similarity() -> None:
    """Identical high similarities yield dynamic tau equal to mean."""
    sims = [0.85, 0.85, 0.85, 0.85]
    tau = compute_adaptive_tau(sims, tau_base=0.70)
    assert tau == 0.85


def test_adv_adaptive_tau_zero_variance_below_threshold() -> None:
    """Identical low similarities are bounded below by base tau 0.70."""
    sims = [0.60, 0.60, 0.60]
    tau = compute_adaptive_tau(sims, tau_base=0.70)
    assert tau == 0.70


def test_adv_adaptive_tau_negative_similarity_values() -> None:
    """Negative cosine similarities must be safely clamped to base tau 0.70."""
    sims = [-0.9, -0.5, -0.2]
    tau = compute_adaptive_tau(sims, tau_base=0.70)
    assert tau == 0.70


def test_adv_adaptive_tau_skewed_distribution_prunes_tail() -> None:
    """High-performing cluster with outlier correctly adapts tau to isolate cluster."""
    sims = [0.95, 0.94, 0.93, 0.92]
    tau = compute_adaptive_tau(sims, tau_base=0.70)
    assert tau > 0.90
    assert tau <= 0.95


def test_adv_adaptive_tau_boundary_exact_threshold() -> None:
    """Verify precision around tau boundary 0.7000."""
    sims = [0.70, 0.70, 0.70]
    assert compute_adaptive_tau(sims, tau_base=0.70) == 0.70


def test_adv_pruning_hard_candidate_budget_cap_25() -> None:
    """Verify that prune_and_rank_candidates strictly caps output at Kh <= 25."""
    candidates = [
        BridgeHopCandidate(
            openalex_id=f"W{i}",
            title=f"Paper {i}",
            hop_level=1,
            cosine_similarity=0.75 + (i * 0.005),
            adaptive_threshold_tau=0.70,
        )
        for i in range(50)
    ]
    surviving = prune_and_rank_candidates(candidates, tau_h=0.70, max_k=25)
    assert len(surviving) == 25
    for c in surviving:
        assert c.cosine_similarity >= 0.70
        assert c.is_pruned is False


def test_adv_pruning_all_below_base_yields_empty() -> None:
    """When all candidate similarities are below tau_h, 0 survive."""
    candidates = [
        BridgeHopCandidate(
            openalex_id=f"W_low_{i}",
            title=f"Low Sim {i}",
            hop_level=2,
            cosine_similarity=0.40 + (i * 0.05),
            adaptive_threshold_tau=0.70,
        )
        for i in range(5)
    ]
    surviving = prune_and_rank_candidates(candidates, tau_h=0.70, max_k=25)
    assert len(surviving) == 0


@pytest.mark.asyncio
async def test_adv_layer3_returns_none_when_all_pruned() -> None:
    """Layer 3 returns None when all candidates in pool fail adaptive threshold."""
    candidates = [
        BridgeHopCandidate(
            openalex_id="W_weak",
            title="Weak Candidate",
            hop_level=2,
            cosine_similarity=0.62,
            adaptive_threshold_tau=0.70,
        )
    ]
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j)

    res = await service.execute_layer3("10.1/a", "10.1/c", candidate_pool=candidates)
    assert res is None
    assert mock_neo4j.execute_write.call_count == 0


@pytest.mark.asyncio
async def test_adv_layer3_survives_with_top_candidate() -> None:
    """Layer 3 selects the top ranked candidate when multiple candidates survive."""
    c1 = BridgeHopCandidate(
        openalex_id="W_good", title="Good", hop_level=2,
        cosine_similarity=0.82, pagerank_score=1.0, adaptive_threshold_tau=0.70,
    )
    c2 = BridgeHopCandidate(
        openalex_id="W_best", title="Best", hop_level=2,
        cosine_similarity=0.91, pagerank_score=5.0, adaptive_threshold_tau=0.70,
    )
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j)

    res = await service.execute_layer3("10.1/a", "10.1/c", candidate_pool=[c1, c2])
    assert res is not None
    assert res.mechanism == BridgeMechanism.STEINER_BEAM_3HOP
    assert len(res.intermediate_nodes) == 1
    assert res.intermediate_nodes[0].openalex_id == "W_best"
    mock_neo4j.execute_write.assert_called_once()


# ==============================================================================
# 5. Search Depth & Materialization Edge Cases
# ==============================================================================

@pytest.mark.asyncio
async def test_adv_max_hops_blocks_deep_layers() -> None:
    """When max_hops < 3, Layer 2 and Layer 3 deep searches are skipped."""
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = [{"connection_type": "none"}]
    mock_openalex = AsyncMock()
    mock_openalex.find_2hop_directed.return_value = []
    mock_openalex.find_2hop_reverse.return_value = []
    mock_openalex.find_bibliographic_coupling.return_value = []
    mock_openalex.find_co_citation.return_value = []

    service = SVPLService(neo4j_service=mock_neo4j, openalex_service=mock_openalex)
    res = await service.find_bridge_pathway("10.1/a", "10.1/b", max_hops=2)

    assert res is None
    assert mock_openalex.fetch_work_references.call_count == 0


@pytest.mark.asyncio
async def test_adv_materialization_openalex_id_fallback() -> None:
    """Intermediate nodes without DOI fall back to OpenAlex ID cleanly."""
    mock_neo4j = AsyncMock()
    service = SVPLService(neo4j_service=mock_neo4j)
    node = BridgeNodeSummary(openalex_id="W_nodoi", doi=None, title="No DOI Work", year=2021)

    await service.materialize_bridge_pathway(
        source_doi="10.1/src", target_doi="10.1/tgt",
        mechanism=BridgeMechanism.DIRECTED_2HOP, hop_distance=2,
        confidence=0.90, intermediate_nodes=[node], run_id="run_test", stage_index=2,
    )
    mock_neo4j.execute_write.assert_called_once()
    _, params = mock_neo4j.execute_write.call_args[0][:2]
    assert params["path_nodes"][0]["doi"] is None
    assert params["path_nodes"][0]["openalex_id"] == "W_nodoi"
