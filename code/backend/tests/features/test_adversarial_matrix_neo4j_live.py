"""Adversarial live Neo4j verification test suite for Milestone M5 Synthesis Matrices.

Validates:
1. persist_section_synthesis_matrix parameterized Cypher query against live Neo4j:
   - Creation of :SectionSynthesisMatrix with run_id and created_in_stage tags.
   - Creation of [:HAS_MATRIX] edge from OutlineSection to SectionSynthesisMatrix.
   - Creation of [:SYNTHESIZES] edges with evidence_text, quantitative_metric,
     citekey, run_id, created_in_stage, updated_at.
2. Fail-loud semantics:
   - Missing paper drops rows and raises MatrixGenerationError on persisted_count mismatch.
   - Missing OutlineSection returns 0 rows and raises MatrixGenerationError.
3. Matrix updates and idempotency (ON MATCH SET).
4. Boundary condition: maximum 5 dimensions across 3 papers (15 cell edges).
5. Text robustness: LaTeX math, quotes, emojis, and pipes in evidence and metrics.
6. Qualitative dimensions with empty metrics.
7. Compensating rollback Cypher (Constitution C5, A15, A49).
8. Markdown file writing, token budget (<800 tokens), and clean removal.
9. Full MatrixService end-to-end generation and persistence.
10. Full MatrixService citation grounding pre-check (CitationHallucinationError 422).
11. Drafting context retrieval and missing file handling.

Complies with Constitution v2.2.1:
- C7: Strict static typing with explicit annotations.
- C8: Pure Neo4j graph-native persistence.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from config import Settings
from core.db.neo4j_service import Neo4jService
from core.errors.enhancement_errors import (
    CitationHallucinationError,
    MatrixGenerationError,
)
from features.drafting.matrix_models import (
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    SectionSynthesisMatrix,
)
from features.drafting.matrix_persistence import (
    _count_tokens,
    persist_matrix_to_neo4j,
    serialize_matrix_to_markdown,
)
from features.drafting.matrix_service import (
    MatrixService,
    format_doi_citekey,
    get_section_matrix_for_drafting,
    load_section_matrix_context,
)


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


async def _cleanup_test_nodes(neo4j: Neo4jService, tag: str, sec_id: str) -> None:
    """Safely detach and delete test entities from live Neo4j."""
    q1 = "MATCH (n) WHERE n.test_tag = $tag DETACH DELETE n"
    q2 = "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id}) DETACH DELETE m"
    await neo4j.execute_write(q1, {"tag": tag})
    await neo4j.execute_write(q2, {"sec_id": sec_id})


async def _seed_section_and_papers(
    neo4j: Neo4jService, tag: str, sec_id: str, dois: list[str]
) -> None:
    """Seed OutlineSection and Papers for live persistence tests."""
    q_sec = "CREATE (s:OutlineSection {id: $sec_id, test_tag: $tag})"
    await neo4j.execute_write(q_sec, {"sec_id": sec_id, "tag": tag})
    q_paper = (
        "UNWIND $dois AS doi "
        "CREATE (p:Paper {doi: doi, title: 'Paper ' + doi, abstract: 'Abstract for ' + doi, "
        "test_tag: $tag, is_stub: false})"
    )
    await neo4j.execute_write(q_paper, {"dois": dois, "tag": tag})


def _build_dimensions(count: int = 3) -> list[AnalyticalDimension]:
    """Generate between 3 and 5 test analytical dimensions."""
    all_dims = [
        AnalyticalDimension(
            dimension_id=f"dim_{i}",
            name=f"Dim {i}",
            description=f"Desc {i}",
            evaluation_type="metric" if i % 2 == 0 else "qualitative",
        )
        for i in range(1, count + 1)
    ]
    return all_dims[:count]


def _build_cell_data(
    dois: list[str], dims: list[AnalyticalDimension]
) -> dict[str, dict[str, CellEvidenceExtract]]:
    """Build nested 2D cell dictionary with valid LaTeX citekeys."""
    cells: dict[str, dict[str, CellEvidenceExtract]] = {}
    for doi in dois:
        cells[doi] = {}
        ck = format_doi_citekey(doi)
        for d in dims:
            metric = "94.2%" if d.evaluation_type == "metric" else None
            cells[doi][d.dimension_id] = CellEvidenceExtract(
                evidence_text=f"Evidence for {d.name} in {doi}",
                quantitative_metric=metric,
                citekey=ck,
                is_grounded=True,
            )
    return cells


def _build_matrix_model(
    sec_id: str,
    dois: list[str],
    dims: list[AnalyticalDimension],
    out_path: str = "test.md",
) -> SectionSynthesisMatrix:
    """Build a valid SectionSynthesisMatrix model with cell extracts."""
    return SectionSynthesisMatrix(
        matrix_id=str(uuid.uuid4()),
        section_id=sec_id,
        section_title="Test Section",
        narrative_theme="Test Theme",
        dimensions=dims,
        assigned_dois=dois,
        verified_dois=dois,
        cell_data=_build_cell_data(dois, dims),
        markdown_path=out_path,
    )


@pytest.mark.asyncio
async def test_live_neo4j_matrix_persistence_contract() -> None:
    """Verify live Neo4j :SectionSynthesisMatrix, [:HAS_MATRIX], and [:SYNTHESIZES] properties."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1", f"10.1145/{tag}_2"]
    dims = _build_dimensions(3)
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, dois)
        matrix = _build_matrix_model(sec_id, dois, dims)
        res = await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        assert res["persisted_count"] == 6
        v_q = (
            "MATCH (s:OutlineSection {id: $sec_id})-[:HAS_MATRIX]->(m:SectionSynthesisMatrix) "
            "MATCH (m)-[r:SYNTHESIZES]->(p:Paper) "
            "RETURN m.run_id AS run_id, m.created_in_stage AS stage, count(r) AS rel_count"
        )
        recs = await neo4j.execute_read(v_q, {"sec_id": sec_id})
        assert len(recs) == 1 and recs[0]["rel_count"] == 6
        assert recs[0]["run_id"] == tag and recs[0]["stage"] == 4
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_fail_loud_ungrounded_doi() -> None:
    """Verify missing paper drops rows and raises MatrixGenerationError on live Neo4j."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, doi1, doi_miss = f"sec_{tag}", f"10.1145/{tag}_1", f"10.1145/{tag}_missing"
    dims = _build_dimensions(3)
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, [doi1])
        matrix = _build_matrix_model(sec_id, [doi1, doi_miss], dims)
        with pytest.raises(MatrixGenerationError, match="Fail-loud grounding failure"):
            await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_fail_loud_missing_outline_section() -> None:
    """Verify non-existent OutlineSection returns 0 rows and raises MatrixGenerationError."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1"]
    dims = _build_dimensions(3)
    try:
        q = "CREATE (p:Paper {doi: $doi, test_tag: $tag})"
        await neo4j.execute_write(q, {"doi": dois[0], "tag": tag})
        matrix = _build_matrix_model(sec_id, dois, dims)
        with pytest.raises(MatrixGenerationError, match="Fail-loud grounding failure"):
            await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_persistence_idempotency_and_update() -> None:
    """Verify repeated persistence updates properties without duplicate nodes."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1"]
    dims = _build_dimensions(3)
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, dois)
        matrix = _build_matrix_model(sec_id, dois, dims)
        await persist_matrix_to_neo4j(neo4j, matrix, run_id=f"run1_{tag}", stage_index=4)
        matrix.narrative_theme = "Updated Theme V2"
        await persist_matrix_to_neo4j(neo4j, matrix, run_id=f"run2_{tag}", stage_index=4)
        recs = await neo4j.execute_read(
            "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id}) "
            "RETURN count(m) AS cnt, m.narrative_theme AS theme, m.run_id AS run_id",
            {"sec_id": sec_id},
        )
        assert recs[0]["cnt"] == 1 and recs[0]["theme"] == "Updated Theme V2"
        assert recs[0]["run_id"] == f"run2_{tag}"
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_max_dimensions_and_multi_paper_grid() -> None:
    """Verify boundary condition: 5 dimensions across 3 papers (15 cell relationships)."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_{i}" for i in range(3)]
    dims = _build_dimensions(5)
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, dois)
        matrix = _build_matrix_model(sec_id, dois, dims)
        res = await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        assert res["persisted_count"] == 15
        q = "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id})-[r:SYNTHESIZES]->() RETURN count(r) AS cnt"
        recs = await neo4j.execute_read(q, {"sec_id": sec_id})
        assert recs[0]["cnt"] == 15
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_special_characters_and_latex_math() -> None:
    """Verify LaTeX math, quotes, emojis, and pipes persist cleanly without corruption."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, doi = f"sec_{tag}", f"10.1145/{tag}_1"
    dims = _build_dimensions(3)
    adv_text = r"Tested: $p < 0.05$ & \sigma = \sqrt{n} | 'quotes' and “smart quotes” ⚡"
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, [doi])
        matrix = _build_matrix_model(sec_id, [doi], dims)
        matrix.cell_data[doi][dims[0].dimension_id].evidence_text = adv_text
        await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        q = "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id})-[r:SYNTHESIZES {dimension_id: $d}]->() RETURN r.evidence_text AS ev"
        recs = await neo4j.execute_read(q, {"sec_id": sec_id, "d": dims[0].dimension_id})
        assert recs[0]["ev"] == adv_text
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_qualitative_cells_empty_metric() -> None:
    """Verify qualitative cells with empty metrics persist empty string on relationship."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, doi = f"sec_{tag}", f"10.1145/{tag}_1"
    dims = [
        AnalyticalDimension(
            dimension_id=f"dim_q_{i}", name=f"Q {i}", description="Desc", evaluation_type="qualitative"
        )
        for i in range(1, 4)
    ]
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, [doi])
        matrix = _build_matrix_model(sec_id, [doi], dims)
        await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        q = "MATCH (m:SectionSynthesisMatrix {section_id: $sec_id})-[r:SYNTHESIZES]->() RETURN r.quantitative_metric AS qm"
        recs = await neo4j.execute_read(q, {"sec_id": sec_id})
        assert len(recs) == 3 and all(r["qm"] == "" for r in recs)
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_compensating_rollback_cypher() -> None:
    """Verify compensating rollback query purges SectionSynthesisMatrix and relationships."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1"]
    dims = _build_dimensions(3)
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, dois)
        matrix = _build_matrix_model(sec_id, dois, dims)
        await persist_matrix_to_neo4j(neo4j, matrix, run_id=tag, stage_index=4)
        rollback_q = "MATCH (n:SectionSynthesisMatrix {run_id: $run_id}) DETACH DELETE n"
        await neo4j.execute_write(rollback_q, {"run_id": tag})
        recs = await neo4j.execute_read("MATCH (n:SectionSynthesisMatrix {run_id: $run_id}) RETURN count(n) AS cnt", {"run_id": tag})
        assert recs[0]["cnt"] == 0
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


def test_live_neo4j_markdown_serialization_and_cleanup(tmp_path: Path) -> None:
    """Verify markdown serialization writes atomic file and cleans up cleanly."""
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1", f"10.1145/{tag}_2"]
    matrix = _build_matrix_model(sec_id, dois, _build_dimensions(3))
    out_file = serialize_matrix_to_markdown(matrix, output_dir=str(tmp_path))
    assert Path(out_file).exists()
    content = Path(out_file).read_text(encoding="utf-8")
    assert "## Synthesis Matrix:" in content
    assert _count_tokens(content) < 800
    Path(out_file).unlink()
    assert not Path(out_file).exists()


@pytest.mark.asyncio
async def test_live_neo4j_service_e2e_generation_and_persistence(tmp_path: Path) -> None:
    """Verify full MatrixService pipeline against live Neo4j with clean teardown."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, dois = f"sec_{tag}", [f"10.1145/{tag}_1", f"10.1145/{tag}_2"]
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, dois)
        svc = MatrixService(neo4j=neo4j)
        inp = GenerateSectionSynthesisMatrixInput(
            project_id=f"p_{tag}", section_id=sec_id, section_title="Evaluation Section",
            narrative_theme="Benchmark rigor and metrics", assigned_dois=dois,
            run_id=tag, stage_index=4
        )
        out = await svc.generate_section_matrix(inp)
        assert out.status == "success" and out.paper_count == 2
        assert len(out.dimensions) >= 3 and Path(out.markdown_path).exists()
        Path(out.markdown_path).unlink()
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


@pytest.mark.asyncio
async def test_live_neo4j_service_citation_hallucination_pre_check() -> None:
    """Verify ungrounded DOI raises CitationHallucinationError without graph mutation."""
    neo4j = await _get_live_neo4j()
    if neo4j is None:
        pytest.skip("Live Neo4j instance not reachable")
    tag = f"test_{uuid.uuid4().hex[:8]}"
    sec_id, doi_real, doi_fake = f"sec_{tag}", f"10.1145/{tag}_real", f"10.1145/{tag}_fake"
    try:
        await _seed_section_and_papers(neo4j, tag, sec_id, [doi_real])
        svc = MatrixService(neo4j=neo4j)
        inp = GenerateSectionSynthesisMatrixInput(
            project_id=f"p_{tag}", section_id=sec_id, section_title="Evaluation",
            narrative_theme="Theme", assigned_dois=[doi_real, doi_fake], run_id=tag, stage_index=4
        )
        with pytest.raises(CitationHallucinationError) as exc_info:
            await svc.generate_section_matrix(inp)
        assert exc_info.value.doi == doi_fake and exc_info.value.http_status_code == 422
        recs = await neo4j.execute_read("MATCH (m:SectionSynthesisMatrix {section_id: $sec_id}) RETURN m", {"sec_id": sec_id})
        assert len(recs) == 0
    finally:
        await _cleanup_test_nodes(neo4j, tag, sec_id)
        await neo4j.close()


def test_live_neo4j_drafting_context_retrieval(tmp_path: Path) -> None:
    """Verify get_section_matrix_for_drafting reads markdown and handles missing files."""
    dummy_file = tmp_path / "sec_test.md"
    dummy_file.write_text("# Test Synthesis Table", encoding="utf-8")
    content1 = get_section_matrix_for_drafting("sec_test", markdown_path=str(dummy_file))
    content2 = load_section_matrix_context("sec_test", markdown_path=str(dummy_file))
    assert content1 == "# Test Synthesis Table"
    assert content2 == "# Test Synthesis Table"
    with pytest.raises(FileNotFoundError):
        get_section_matrix_for_drafting("missing_sec", markdown_path=str(tmp_path / "absent.md"))
