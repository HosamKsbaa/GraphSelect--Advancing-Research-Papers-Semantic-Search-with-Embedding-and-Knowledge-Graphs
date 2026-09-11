"""Adversarial live Neo4j verification test suite for Milestone M4 Gap Analysis.

Validates:
1. calculate_rq_coverage parameterized Cypher query against live Neo4j:
   - Zero library papers returns 0.0 coverage.
   - Low-similarity papers (< 0.70) filtered out.
   - Opposing / negative similarity filtered out.
   - Stub papers (is_stub=True) filtered out.
   - NULL paper or RQ embeddings handled gracefully without exceptions.
   - Unlinked papers (missing [:CONTAINS]) excluded.
   - Exact cosine sum and k_target scaling.
   - Coverage score capping at 1.0.
   - Non-existent project or research question handling.
2. flag_open_research_frontier Cypher query against live Neo4j:
   - Valid node property persistence (is_open_frontier, notes, run_id, updated_at).
   - Idempotent updates on re-flagging.
   - Handling non-existent research questions.
   - Unicode, quotes, and special characters in remediation notes.
3. RECORD_REMEDIATION_CYCLE_CYPHER execution and relationship linkage.

Complies with Constitution v2.2.1:
- C7: Strict static typing with explicit annotations.
- C8: Pure Neo4j graph-native persistence.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from config import Settings
from core.db.neo4j_service import Neo4jService
from features.gap_analysis.coverage_calculator import calculate_question_coverage
from features.gap_analysis.remediation_service import RECORD_REMEDIATION_CYCLE_CYPHER


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


async def _cleanup_tagged_nodes(neo4j: Neo4jService, tag: str) -> None:
    """Safely delete all live test entities created under test tag."""
    query = "MATCH (n) WHERE n.test_tag = $tag DETACH DELETE n"
    await neo4j.execute_write(query, {"tag": tag})


async def _seed_project_and_rq(
    neo4j: Neo4jService, tag: str, pid: str, qid: str, rq_emb: list[float] | None = None
) -> None:
    """Seed live Project and ResearchQuestion nodes."""
    query = (
        "CREATE (pr:Project {project_id: $pid, test_tag: $tag}) "
        "CREATE (rq:ResearchQuestion {question_id: $qid, test_tag: $tag, is_open_frontier: false}) "
        "SET rq.embedding = $rq_emb"
    )
    await neo4j.execute_write(query, {"pid": pid, "qid": qid, "tag": tag, "rq_emb": rq_emb})


async def _seed_paper(
    neo4j: Neo4jService,
    tag: str,
    pid: str,
    doi: str,
    emb: list[float] | None = None,
    is_stub: bool = False,
    link_proj: bool = True,
) -> None:
    """Seed live Paper node and optionally link to Project via :CONTAINS."""
    create_q = "CREATE (p:Paper {doi: $doi, test_tag: $tag, is_stub: $is_stub}) SET p.embedding = $emb"
    await neo4j.execute_write(create_q, {"doi": doi, "tag": tag, "is_stub": is_stub, "emb": emb})
    if link_proj:
        link_q = "MATCH (pr:Project {project_id: $pid}), (p:Paper {doi: $doi}) MERGE (pr)-[:CONTAINS]->(p)"
        await neo4j.execute_write(link_q, {"pid": pid, "doi": doi})


@pytest.mark.asyncio
async def test_live_neo4j_coverage_zero_library_papers() -> None:
    """Zero library papers in project yields 0 qualifying count and 0.0 coverage."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0, 0.0])
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid)
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_papers_below_relevance_threshold() -> None:
    """Papers with Neo4j cosine similarity below min_relevance are filtered out."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_low1_{tag}", [0.2, 0.9798, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_low2_{tag}", [0.0, 1.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_opp_{tag}", [-1.0, 0.0, 0.0])
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid, min_relevance=0.70)
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_stubs_and_null_embeddings_filtered() -> None:
    """Stub papers and NULL embeddings are excluded from coverage calculation."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_stub_{tag}", [1.0, 0.0], is_stub=True)
        await _seed_paper(neo4j, tag, pid, f"doi_null_{tag}", None, is_stub=False)
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid)
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_unlinked_papers_filtered() -> None:
    """Papers not linked via :CONTAINS relationship are excluded from coverage."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_unlinked_{tag}", [1.0, 0.0], link_proj=False)
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid)
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_exact_similarity_and_k_target_scaling() -> None:
    """Qualifying papers sum Neo4j similarity and scale by k_target accurately."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_1_{tag}", [1.0, 0.0])
        await _seed_paper(neo4j, tag, pid, f"doi_2_{tag}", [0.8, 0.6])
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid, min_relevance=0.70, k_target=3.0)
        assert count == 2
        assert abs(raw - (1.90 / 3.0)) < 1e-4
        assert score == 0.633
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_score_capped_at_unity() -> None:
    """Coverage score caps strictly at 1.0 when raw coverage exceeds unity."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, [1.0, 0.0])
        for i in range(4):
            await _seed_paper(neo4j, tag, pid, f"doi_{i}_{tag}", [1.0, 0.0])
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid, min_relevance=0.70, k_target=3.0)
        assert count == 4
        assert raw > 1.0
        assert score == 1.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_nonexistent_project_or_rq() -> None:
    """Non-existent project or research question yields 0 count and 0.0 coverage."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    try:
        count, raw, score = await calculate_question_coverage(neo4j, "missing_proj", "missing_rq")
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_coverage_null_rq_embedding() -> None:
    """ResearchQuestion with NULL embedding safely returns 0 coverage without error."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    pid, qid = f"proj_{tag}", f"rq_{tag}"
    try:
        await _seed_project_and_rq(neo4j, tag, pid, qid, rq_emb=None)
        await _seed_paper(neo4j, tag, pid, f"doi_p_{tag}", [1.0, 0.0])
        count, raw, score = await calculate_question_coverage(neo4j, pid, qid)
        assert count == 0
        assert raw == 0.0
        assert score == 0.0
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_flag_open_research_frontier_success() -> None:
    """Verify flag_open_research_frontier sets all required properties on live node."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    qid = f"rq_{tag}"
    try:
        await neo4j.execute_write("CREATE (rq:ResearchQuestion {question_id: $qid, test_tag: $tag, is_open_frontier: false})", {"qid": qid, "tag": tag})
        notes = "Exhausted 3 iterations: coverage 0.450 < 0.700"
        res = await neo4j.flag_open_research_frontier(qid, notes, f"run_{tag}")
        assert res["rq_id"] == qid
        assert res["is_open_frontier"] is True
        db_recs = await neo4j.execute_read("MATCH (rq:ResearchQuestion {question_id: $qid}) RETURN rq.is_open_frontier AS is_open, rq.remediation_notes AS notes, rq.remediation_run_id AS run_id, rq.updated_at AS upd", {"qid": qid})
        assert len(db_recs) == 1
        assert db_recs[0]["is_open"] is True
        assert db_recs[0]["notes"] == notes
        assert db_recs[0]["run_id"] == f"run_{tag}"
        assert db_recs[0]["upd"] is not None
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_flag_open_research_frontier_idempotent_update() -> None:
    """Verify repeated calls update notes, run_id, and timestamp idempotently."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    qid = f"rq_{tag}"
    try:
        await neo4j.execute_write("CREATE (rq:ResearchQuestion {question_id: $qid, test_tag: $tag, is_open_frontier: false})", {"qid": qid, "tag": tag})
        await neo4j.flag_open_research_frontier(qid, "First notes", f"run_first_{tag}")
        res2 = await neo4j.flag_open_research_frontier(qid, "Updated notes", f"run_second_{tag}")
        assert res2["is_open_frontier"] is True
        db_recs = await neo4j.execute_read("MATCH (rq:ResearchQuestion {question_id: $qid}) RETURN rq.remediation_notes AS notes, rq.remediation_run_id AS run_id", {"qid": qid})
        assert db_recs[0]["notes"] == "Updated notes"
        assert db_recs[0]["run_id"] == f"run_second_{tag}"
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_flag_open_research_frontier_nonexistent_rq() -> None:
    """Non-existent ResearchQuestion does not throw exception and returns fallback."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    try:
        res = await neo4j.flag_open_research_frontier("missing_rq_id", "Notes", "run_x")
        assert res["rq_id"] == "missing_rq_id"
        assert res["is_open_frontier"] is True
    finally:
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_flag_open_research_frontier_special_chars() -> None:
    """Remediation notes containing quotes, LaTeX, and Unicode persist cleanly."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    qid = f"rq_{tag}"
    notes = r"Deficit: 'N=0' with $C(RQ_i) < 0.70$ & \cite{test} — ‘frontier’ 🚀"
    try:
        await neo4j.execute_write("CREATE (rq:ResearchQuestion {question_id: $qid, test_tag: $tag, is_open_frontier: false})", {"qid": qid, "tag": tag})
        await neo4j.flag_open_research_frontier(qid, notes, f"run_{tag}")
        recs = await neo4j.execute_read("MATCH (rq:ResearchQuestion {question_id: $qid}) RETURN rq.remediation_notes AS notes", {"qid": qid})
        assert recs[0]["notes"] == notes
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_record_remediation_cycle_persistence() -> None:
    """Verify RECORD_REMEDIATION_CYCLE_CYPHER creates cycle node and HAD_REMEDIATION_CYCLE edge."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j DBMS not available")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    qid, cid = f"rq_{tag}", f"cycle_{tag}"
    try:
        await neo4j.execute_write("CREATE (rq:ResearchQuestion {question_id: $qid, test_tag: $tag})", {"qid": qid, "tag": tag})
        params = {"rq_id": qid, "cycle_id": cid, "iteration": 1, "initial_cov": 0.33, "resulting_cov": 0.66, "delta": 0.33, "status": "iterating", "queries": ["q1"], "retrieved_dois": ["10.1/a"], "accepted_dois": ["10.1/a"], "run_id": f"run_{tag}", "created_in_stage": 2}
        await neo4j.execute_write(RECORD_REMEDIATION_CYCLE_CYPHER, params)
        recs = await neo4j.execute_read("MATCH (rq:ResearchQuestion {question_id: $qid})-[:HAD_REMEDIATION_CYCLE]->(c:RemediationCycle {cycle_id: $cid}) RETURN c.iteration AS it, c.status AS st, c.queries AS q", {"qid": qid, "cid": cid})
        assert len(recs) == 1
        assert recs[0]["it"] == 1
        assert recs[0]["st"] == "iterating"
        assert recs[0]["q"] == ["q1"]
    finally:
        await _cleanup_tagged_nodes(neo4j, tag)
        await neo4j.close()
