"""Tier 5 Adversarial Coverage Hardening & Cross-Feature Stress Testing (Milestone M7).

Empirically tests and stress-tests:
1. Cross-pipeline integration: Ingestion -> Relevance Gate -> Gap Remediation -> SVPL Bridge -> Section Matrix.
2. Malformed Unicode, mixed scripts (Arabic, Chinese, Cyrillic), Zalgo, emoji, and markdown injection.
3. Extreme similarity distributions in Steiner Beam adaptive pruning (tau_h) and Kh <= 25 budget caps.
4. Token budget progressive truncation (<800 tokens) under massive (5,000+ char) evidence cells.
5. Strict necessity gating (FR-015) and zero citation hallucination (A37, CHR == 0.0%).

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C8: Pure Neo4j graph SSOT, zero MySQL.
- C9: Every function is strictly <= 25 lines (SRP & SLAP).
- C10: Early returns, guard clauses, and obvious control flow.
- A37: Zero citation hallucination ($CHR \\equiv 0.0\\%$).
- FR-011: Kh <= 25 candidate budget cap.
- FR-015: Strict necessity-gated SVPL multi-hop.
- FR-016: Relevance gate threshold (0.75).
- SC-006: Under 800 token serialized markdown footprint.
"""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.errors.enhancement_errors import (
    CitationHallucinationError,
    MatrixGenerationError,
    MultiHopUnauthorizedError,
)
from features.drafting.matrix_models import (
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    SectionSynthesisMatrix,
)
from features.drafting.matrix_persistence import (
    _count_tokens,
    _enforce_token_budget,
    _format_cell_content,
    serialize_matrix_to_markdown,
)
from features.drafting.matrix_service import (
    MatrixService,
    assert_citation_grounding,
    extract_cell_evidence,
    format_doi_citekey,
)
from features.gap_analysis.models import (
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
)
from features.gap_analysis.remediation_service import RemediationService
from features.ingestion.identifier_extractor import (
    clean_punctuation,
    compute_title_similarity,
    extract_all_identifiers,
    extract_dois,
)
from features.ingestion.models import IdentifierType
from features.ingestion.relevance_gate import evaluate_paper_relevance
from features.ranking.svpl_gating import (
    check_multihop_authorization,
    is_multihop_authorized,
)
from features.ranking.svpl_models import (
    BridgeHopCandidate,
    BridgeMechanism,
    BridgeNodeSummary,
    MultiHopBridgePathway,
    MultiHopTriggerReason,
)
from features.ranking.svpl_service import (
    SVPLService,
    compute_adaptive_tau,
    prune_and_rank_candidates,
)


def _make_mock_neo4j() -> MagicMock:
    """Instantiate mock Neo4jService with async execution methods."""
    neo = MagicMock()
    neo.execute_read = AsyncMock()
    neo.execute_write = AsyncMock()
    neo.flag_open_research_frontier = AsyncMock()
    return neo


def _make_mock_openalex() -> MagicMock:
    """Instantiate mock OpenAlexService with async lookup methods."""
    oa = MagicMock()
    oa.search_by_title = AsyncMock(return_value=[])
    oa.find_2hop_directed = AsyncMock(return_value=[])
    oa.fetch_work_references = AsyncMock(return_value=[])
    return oa


def _make_dim(dim_id: str, name: str) -> AnalyticalDimension:
    """Construct AnalyticalDimension fixture model."""
    return AnalyticalDimension(
        dimension_id=dim_id,
        name=name,
        description=f"Evaluation of {name}",
        evaluation_type="qualitative",
    )


# ==============================================================================
# 1. Malformed Unicode, Mixed Scripts, Zalgo, and Markdown Injections
# ==============================================================================


def test_adv_unicode_multilingual_doi_extraction() -> None:
    """Extract DOIs cleanly from Arabic, Chinese, Cyrillic, and emoji sentences."""
    texts = [
        "اقرأ هذا البحث 10.1038/nature12345 ممتاز",
        "最新论文参考：10.1145/3292500，强烈推荐。",
        "См. статью 10.1016/j.cell.2024.01.001 здесь.",
        "🤖📚🔬 Check breakthrough 10.1007/s00222-011-0315-4 🚀!",
        "\u202e10.1038/nature12345\u202c (RTL override wrapped)",
    ]
    dois = [extract_dois(t)[0] for t in texts]
    assert dois == [
        "10.1038/nature12345",
        "10.1145/3292500",
        "10.1016/j.cell.2024.01.001",
        "10.1007/s00222-011-0315-4",
        "10.1038/nature12345",
    ]


def test_adv_zalgo_and_control_char_title_similarity() -> None:
    """Verify title similarity computes bounded float under Zalgo and zero-width spaces."""
    zalgo = "D̸e̸e̸p̸ L̸e̸a̸r̸n̸i̸n̸g̸"
    normal = "Deep Learning"
    score_zalgo = compute_title_similarity(zalgo, normal)
    assert 0.0 <= score_zalgo <= 1.0

    zw_title = "Deep\u200bLearning\u200cModels"
    clean_title = "Deep Learning Models"
    score_zw = compute_title_similarity(zw_title, clean_title)
    assert 0.0 <= score_zw <= 1.0


def test_adv_clean_punctuation_exotic_characters() -> None:
    """Clean punctuation strips fullwidth brackets, guillemets, and smart quotes."""
    samples = [
        ("《10.1038/nature12345》", "10.1038/nature12345"),
        ("【10.1145/3292500】", "10.1145/3292500"),
        ("«10.1016/j.cell.2024.01.001»", "10.1016/j.cell.2024.01.001"),
        ("“‘10.1007/s00222-011-0315-4’”…", "10.1007/s00222-011-0315-4"),
    ]
    for raw, expected in samples:
        dois = extract_dois(raw)
        assert len(dois) == 1 and dois[0] == expected


def test_adv_cell_content_pipe_and_newline_escaping() -> None:
    """Ensure cell formatter escapes pipes and replaces newlines to protect markdown tables."""
    raw_evidence = "Result | with | pipes \n and \r\n newlines <script>alert(1)</script>"
    cell = CellEvidenceExtract(
        evidence_text=raw_evidence,
        quantitative_metric="95.4%",
        citekey=format_doi_citekey("10.1000/test"),
        is_grounded=True,
    )
    formatted = _format_cell_content(cell, max_chars=200)
    assert "\\|" in formatted
    assert "\n" not in formatted
    assert formatted.startswith("**95.4%**:")


# ==============================================================================
# 2. Steiner Beam Adaptive Pruning (tau_h) & Extreme Distributions
# ==============================================================================


def test_adv_adaptive_tau_empty_and_single_element() -> None:
    """Empty and single-element distributions return expected tau bounds."""
    assert compute_adaptive_tau([], tau_base=0.70) == 0.70
    assert compute_adaptive_tau([0.25], tau_base=0.70) == 0.70
    assert compute_adaptive_tau([0.85], tau_base=0.70) == 0.85


def test_adv_adaptive_tau_zero_variance_identical_scores() -> None:
    """Zero variance distribution returns mean exactly without division errors."""
    scores = [0.88, 0.88, 0.88, 0.88, 0.88]
    assert compute_adaptive_tau(scores, tau_base=0.70) == 0.88


def test_adv_adaptive_tau_negative_and_zero_similarities() -> None:
    """Negative and zero similarities never drop below tau_base."""
    negatives = [-0.8, -0.4, -0.1, 0.0]
    assert compute_adaptive_tau(negatives, tau_base=0.70) == 0.70
    zeros = [0.0, 0.0, 0.0]
    assert compute_adaptive_tau(zeros, tau_base=0.70) == 0.70


def test_adv_adaptive_tau_extreme_outlier_skew() -> None:
    """Extreme bimodal outlier distribution respects tau_base floor."""
    skewed = [0.99] + [0.10] * 50
    tau = compute_adaptive_tau(skewed, tau_base=0.70)
    assert tau >= 0.70


def test_adv_prune_and_rank_all_candidates_pruned() -> None:
    """When all candidates fall below tau_h, surviving list is empty."""
    cands = [
        BridgeHopCandidate(
            openalex_id=f"W{i}",
            doi=f"10.1000/{i}",
            title=f"Paper {i}",
            hop_level=1,
            cosine_similarity=0.50 + (i * 0.02),
            adaptive_threshold_tau=0.75,
            pagerank_score=0.01,
        )
        for i in range(5)
    ]
    surviving = prune_and_rank_candidates(cands, tau_h=0.75, max_k=25)
    assert len(surviving) == 0
    assert all(c.is_pruned for c in cands)


def test_adv_prune_and_rank_kh_cap_enforced_at_25() -> None:
    """Candidate pool over 25 papers is strictly capped at Kh <= 25 (FR-011)."""
    cands = [
        BridgeHopCandidate(
            openalex_id=f"W{i}",
            doi=f"10.1000/{i}",
            title=f"Paper {i}",
            hop_level=1,
            cosine_similarity=0.80 + (i * 0.002),
            adaptive_threshold_tau=0.70,
            pagerank_score=0.01,
        )
        for i in range(50)
    ]
    surviving = prune_and_rank_candidates(cands, tau_h=0.70, max_k=25)
    assert len(surviving) == 25
    assert all(not c.is_pruned for c in surviving)


# ==============================================================================
# 3. Token Budget Truncation Under Massive (5000+ char) Evidence Cells
# ==============================================================================


def _build_massive_cell_data(
    dois: list[str], dims: list[AnalyticalDimension]
) -> dict[str, dict[str, CellEvidenceExtract]]:
    """Build cell data dictionary with massive 5,000+ char extracts."""
    massive_text = "Detailed findings on empirical scalability. " * 120  # ~5,200 chars
    return {
        doi: {
            d.dimension_id: CellEvidenceExtract(
                evidence_text=massive_text,
                quantitative_metric="p < 0.01",
                citekey=format_doi_citekey(doi),
                is_grounded=True,
            )
            for d in dims
        }
        for doi in dois
    }


def _build_massive_matrix(
    dims: list[AnalyticalDimension], dois: list[str]
) -> SectionSynthesisMatrix:
    """Construct SectionSynthesisMatrix model with massive evidence cells."""
    cell_data = _build_massive_cell_data(dois, dims)
    return SectionSynthesisMatrix(
        matrix_id="m_massive_01",
        section_id="sec_massive",
        section_title="Massive Stress Section",
        narrative_theme="High density evidence evaluation",
        dimensions=dims,
        assigned_dois=dois,
        verified_dois=dois,
        cell_data=cell_data,
        markdown_path="stage_04_artifacts/matrices/sec_massive.md",
    )


def test_adv_massive_evidence_cells_token_budget_truncation() -> None:
    """Massive 5,000-char evidence cells are progressively truncated under 800 tokens."""
    dims = [_make_dim(f"d{i}", f"Dimension {i}") for i in range(4)]
    dois = [f"10.1000/paper_{i}" for i in range(3)]
    matrix = _build_massive_matrix(dims, dois)
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = serialize_matrix_to_markdown(matrix, output_dir=tmp_dir)
        content = Path(out_path).read_text(encoding="utf-8")
        assert _count_tokens(content) < 800
        table_rows = [line for line in content.splitlines() if line.startswith("|")]
        for row in table_rows:
            assert row.count("|") == 6


def _build_dense_matrix() -> SectionSynthesisMatrix:
    """Construct dense matrix fixture for progressive cascade testing."""
    dims = [_make_dim(f"d{i}", f"Analytical Theme {i}") for i in range(5)]
    dois = [f"10.1000/p_{i}" for i in range(5)]
    cell_data = {
        doi: {
            d.dimension_id: CellEvidenceExtract(
                evidence_text="Extremely long verbose academic finding text " * 50,
                quantitative_metric="88.2%",
                citekey=format_doi_citekey(doi),
            )
            for d in dims
        }
        for doi in dois
    }
    return SectionSynthesisMatrix(
        matrix_id="m_prog", section_id="sec_prog", section_title="Theme Progression",
        narrative_theme="Progression", dimensions=dims, assigned_dois=dois,
        verified_dois=dois, cell_data=cell_data, markdown_path="matrices/sec_prog.md",
    )


def test_adv_progressive_token_enforcement_cascade() -> None:
    """Progressive truncation cascades downward to 40 chars under extreme token load."""
    matrix = _build_dense_matrix()
    rendered = _enforce_token_budget(matrix, max_tokens=780)
    assert _count_tokens(rendered) <= 780


# ==============================================================================
# 4. Cross-Feature Integrated Scenarios
# ==============================================================================


def test_adv_cross_pipeline_relevance_gate_branching() -> None:
    """Continuous ingestion relevance gate blocks deep expansion at 0.7499, allows at 0.7500."""
    rq_vec = [1.0, 0.0]
    # cos = 0.7499
    angle_below = math.acos(0.7499)
    vec_below = [math.cos(angle_below), math.sin(angle_below)]
    can_expand, score_below = evaluate_paper_relevance(vec_below, [rq_vec], threshold=0.75)
    assert can_expand is False
    assert round(score_below, 4) == 0.7499

    # cos = 0.7501
    angle_above = math.acos(0.7501)
    vec_above = [math.cos(angle_above), math.sin(angle_above)]
    can_expand_above, score_above = evaluate_paper_relevance(vec_above, [rq_vec], threshold=0.75)
    assert can_expand_above is True
    assert round(score_above, 4) == 0.7501

    # user override allows expansion regardless of low cosine
    can_override, _ = evaluate_paper_relevance(vec_below, [rq_vec], threshold=0.75, is_user_override=True)
    assert can_override is True


@pytest.mark.asyncio
async def test_adv_cross_pipeline_citation_hallucination_prevents_persistence() -> None:
    """Drafting agent requesting matrix with unverified DOI triggers loud error and zero writes."""
    neo = _make_mock_neo4j()
    # Neo4j only has paper_1, not paper_2
    neo.execute_read.return_value = [
        {"doi": "10.1000/paper_1", "title": "Paper 1", "abstract": "Abstract 1 with 45% gain."}
    ]
    service = MatrixService(neo4j=neo)
    input_data = GenerateSectionSynthesisMatrixInput(
        project_id="proj_adv",
        section_id="sec_hallucination",
        section_title="Hallucination Test",
        narrative_theme="Verification",
        assigned_dois=["10.1000/paper_1", "10.1000/paper_hallucinated"],
        run_id="run_adv_hallucination",
    )

    with pytest.raises(CitationHallucinationError) as exc_info:
        await service.generate_section_matrix(input_data)

    assert exc_info.value.doi == "10.1000/paper_hallucinated"
    neo.execute_write.assert_not_called()


def _make_mock_svpl_with_bridge(bridge_doi: str) -> MagicMock:
    """Instantiate mock SVPLService returning 2-hop bridge pathway."""
    svpl = MagicMock()
    pathway = MultiHopBridgePathway(
        pathway_id="pw_bridge_01",
        source_doi="10.1000/anchor_src",
        target_doi="10.1000/anchor_tgt",
        intermediate_nodes=[
            BridgeNodeSummary(
                openalex_id="W999", doi=bridge_doi, title="Bridge Paper",
                year=2023, is_stub=True,
            )
        ],
        mechanism=BridgeMechanism.DIRECTED_2HOP,
        discovered_layer=1,
        confidence=0.95,
        hop_distance=2,
    )
    svpl.find_bridge_pathway = AsyncMock(return_value=pathway)
    return svpl


@pytest.mark.asyncio
async def test_adv_cross_pipeline_gap_n0_triggers_svpl_cascade() -> None:
    """Candidate count N=0 autonomously triggers SVPL with empty_gap_remediation reason."""
    neo, oa = _make_mock_neo4j(), _make_mock_openalex()
    oa.search_by_title.return_value = []
    svpl = _make_mock_svpl_with_bridge("10.1000/bridge_node")

    remediation = RemediationService(neo4j=neo, openalex=oa, svpl_service=svpl)
    candidates = await remediation.retrieve_candidate_papers(
        queries=["quantum computing benchmark"], project_id="proj_test",
        source_doi="10.1000/anchor_src", target_doi="10.1000/anchor_tgt",
    )
    assert len(candidates) == 1 and candidates[0]["doi"] == "10.1000/bridge_node"
    svpl.find_bridge_pathway.assert_awaited_once_with(
        source_doi="10.1000/anchor_src", target_doi="10.1000/anchor_tgt",
        project_id="proj_test",
        trigger_reason=MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
        candidate_count=0, run_id=None, stage_index=2,
    )


def test_adv_cross_pipeline_gap_n_gt_0_forbids_svpl() -> None:
    """When candidate count N > 0, SVPL invocation is strictly forbidden with HTTP 403."""
    with pytest.raises(MultiHopUnauthorizedError) as exc_info:
        check_multihop_authorization(
            MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
            candidate_count=2,
        )
    assert exc_info.value.http_status_code == 403
    assert is_multihop_authorized(MultiHopTriggerReason.EMPTY_GAP_REMEDIATION, candidate_count=2) is False


@pytest.mark.asyncio
async def test_adv_cross_pipeline_terminal_mode_targeted() -> None:
    """Remediation in targeted mode flags open research frontier when deficit remains."""
    neo, oa = _make_mock_neo4j(), _make_mock_openalex()
    neo.execute_read.return_value = [{"qualifying_count": 1, "coverage_score": 0.45}]
    remediation = RemediationService(neo4j=neo, openalex=oa)
    inp = RunAutonomousGapRemediationInput(
        project_id="proj_1", rq_id="rq_target", mode=RemediationMode.TARGETED,
        run_id="run_targeted", max_iterations=1,
    )
    out = await remediation.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.OPEN_RESEARCH_FRONTIER
    assert out.is_open_frontier is True
    neo.flag_open_research_frontier.assert_awaited()


@pytest.mark.asyncio
async def test_adv_cross_pipeline_terminal_mode_exploration() -> None:
    """Remediation in exploration mode pauses awaiting input when deficit remains."""
    neo, oa = _make_mock_neo4j(), _make_mock_openalex()
    neo.execute_read.return_value = [{"qualifying_count": 1, "coverage_score": 0.45}]
    remediation = RemediationService(neo4j=neo, openalex=oa)
    inp = RunAutonomousGapRemediationInput(
        project_id="proj_1", rq_id="rq_explore", mode=RemediationMode.EXPLORATION,
        run_id="run_explore", max_iterations=1,
    )
    out = await remediation.run_remediation_loop(inp)
    assert out.status == RemediationCycleStatus.MAX_ITERATIONS_PAUSED
    assert out.is_open_frontier is False


def _make_e2e_neo4j_mock() -> MagicMock:
    """Construct Neo4j mock returning grounded papers and dynamic matrix write count."""
    neo = _make_mock_neo4j()
    neo.execute_read.return_value = [
        {"doi": "10.1016/j.cell.2024.01.001", "title": "Paper Cell", "abstract": "Improved accuracy by 15.2%."},
        {"doi": "10.1038/nature12345", "title": "Paper Nature", "abstract": "Speed increased 3x on benchmark."},
    ]

    async def _mock_write(_q: str, p: dict[str, Any]) -> list[dict[str, Any]]:
        count = len(p.get("cell_entries", []))
        return [{"matrix_id": "m_e2e_01", "persisted_count": count}]

    neo.execute_write = AsyncMock(side_effect=_mock_write)
    return neo


@pytest.mark.asyncio
async def test_adv_cross_pipeline_e2e_verified_synthesis_flow() -> None:
    """Full cross-pipeline: continuous ingestion wires papers -> matrix service grounds & persists."""
    neo = _make_e2e_neo4j_mock()
    service = MatrixService(neo4j=neo)
    input_data = GenerateSectionSynthesisMatrixInput(
        project_id="proj_cross_e2e", section_id="sec_cross_01",
        section_title="Comparative Deep Ingestion", narrative_theme="High-throughput evaluation",
        assigned_dois=["10.1016/j.cell.2024.01.001", "10.1038/nature12345"],
        run_id="run_cross_e2e",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "features.drafting.matrix_service.serialize_matrix_to_markdown",
                lambda m: serialize_matrix_to_markdown(m, output_dir=tmp_dir),
            )
            output = await service.generate_section_matrix(input_data)
    assert output.status == "success" and output.paper_count == 2
    assert len(output.dimensions) >= 3 and len(output.verified_dois) == 2
    neo.execute_write.assert_awaited_once()
