"""Unit tests for agent tools across literature discovery, analysis, synthesis, and project orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.tools.analysis_tools import (
    extract_paper_findings,
    generate_comparison_matrix,
    synthesize_evidence,
)
from agents.research.tools.retrieval_tools import (
    add_paper_to_project,
    explore_paper,
    get_project_papers,
    run_graphselect_traversal,
)
from agents.research.tools.search_tools import (
    add_research_question,
    get_top_authors,
    get_top_venues,
    list_research_questions,
    search_papers_by_author,
    search_papers_by_doi,
    search_papers_by_keyword,
    search_papers_by_title,
    search_papers_by_venue,
)
from agents.writing.tools.export_tools import export_citation_graph
from core.llm.models import CompletionResponse, TokenUsage


@pytest.fixture
def mock_tool_context() -> ToolContext:
    """Mock ADK ToolContext with a dummy project_id in state."""
    context = MagicMock(spec=ToolContext)
    context.state = MagicMock()
    context.state.get.side_effect = lambda key, default=None: "project-123" if key == "project_id" else default
    return context


@pytest.mark.asyncio
async def test_get_top_authors_success(mock_tool_context: ToolContext) -> None:
    """Test get_top_authors returns list of top authors successfully."""
    mock_records = [
        {"name": "Alice Smith", "openalex_id": "A111", "paper_count": 5},
        {"name": "Bob Jones", "openalex_id": "A222", "paper_count": 3},
    ]
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = mock_records

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        result = await get_top_authors(limit=5, tool_context=mock_tool_context)
        assert "authors" in result
        assert result["total"] == 2

        authors: list[dict[str, Any]] = result["authors"]  # type: ignore[assignment]
        assert authors[0]["name"] == "Alice Smith"
        assert authors[0]["paper_count"] == 5
        assert authors[1]["openalex_id"] == "A222"

        mock_neo4j.execute_read.assert_called_once()
        query = mock_neo4j.execute_read.call_args[0][0]
        params = mock_neo4j.execute_read.call_args[0][1]
        assert "MATCH (pr:Project" in query
        assert "MATCH (a:Author)-[:AUTHORED]" in query
        assert params["project_id"] == "project-123"
        assert params["limit"] == 5
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            delattr(ServiceRegistry, "_neo4j")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_get_top_venues_success(mock_tool_context: ToolContext) -> None:
    """Test get_top_venues returns list of top venues successfully."""
    mock_records = [
        {"name": "Nature GNN", "openalex_id": "V999", "paper_count": 12},
    ]
    mock_neo4j = AsyncMock()
    mock_neo4j.execute_read.return_value = mock_records

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        result = await get_top_venues(limit=3, tool_context=mock_tool_context)
        assert "venues" in result
        assert result["total"] == 1

        venues: list[dict[str, Any]] = result["venues"]  # type: ignore[assignment]
        assert venues[0]["name"] == "Nature GNN"
        assert venues[0]["paper_count"] == 12

        mock_neo4j.execute_read.assert_called_once()
        query = mock_neo4j.execute_read.call_args[0][0]
        params = mock_neo4j.execute_read.call_args[0][1]
        assert "[:PUBLISHED_IN]->(v:Venue)" in query
        assert params["project_id"] == "project-123"
        assert params["limit"] == 3
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            delattr(ServiceRegistry, "_neo4j")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_search_papers_by_keyword_success(mock_tool_context: ToolContext) -> None:
    """Test search_papers_by_keyword returns paper metadata."""
    mock_openalex = AsyncMock()
    mock_openalex.search_by_title = AsyncMock(return_value=[
        MagicMock(doi="10.1000/1", title="GNN Paper", year=2024, cited_by_count=10, authors=["Author A"])
    ])

    old_oa = getattr(ServiceRegistry, "_openalex", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._openalex = mock_openalex
    ServiceRegistry._initialized = True

    try:
        res = await search_papers_by_keyword(query="GNN", max_results=5, tool_context=mock_tool_context)
        assert "papers" in res
        assert res["total_returned"] == 1
        assert res["papers"][0]["doi"] == "10.1000/1"
    finally:
        if old_oa is not None:
            ServiceRegistry._openalex = old_oa
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_search_papers_by_doi_success(mock_tool_context: ToolContext) -> None:
    """Test search_papers_by_doi retrieves paper by DOI."""
    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=MagicMock(
        doi="10.1000/exact", title="Exact Paper", year=2023, abstract="Abstract", cited_by_count=15, openalex_id="W1"
    ))

    old_oa = getattr(ServiceRegistry, "_openalex", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._openalex = mock_openalex
    ServiceRegistry._initialized = True

    try:
        res = await search_papers_by_doi(doi="10.1000/exact", tool_context=mock_tool_context)
        assert res["found"] is True
        assert res["paper"]["title"] == "Exact Paper"
    finally:
        if old_oa is not None:
            ServiceRegistry._openalex = old_oa
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_explore_paper_tool(mock_tool_context: ToolContext) -> None:
    """Test explore_paper tool computes similarity scores and returns graph metadata."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value={
        "doi": "10.1000/exp",
        "title": "Explored Paper",
        "year": 2022,
        "abstract": "Deep exploration abstract.",
        "authors": ["Researcher A"],
        "venue": "NeurIPS",
        "references": ["10.1/ref1"],
        "citations": ["10.1/cit1"],
    })
    mock_neo4j.get_research_questions = AsyncMock(return_value=["Question 1"])
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/exp", "question": "Question 1", "score": 0.88}
    ])

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        res = await explore_paper(doi="10.1000/exp", tool_context=mock_tool_context)
        assert res["doi"] == "10.1000/exp"
        assert res["title"] == "Explored Paper"
        assert res["already_in_graph"] is True
        assert len(res["similarity_scores"]) == 1
        assert res["similarity_scores"][0]["score"] == 0.88
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_add_and_list_research_questions(mock_tool_context: ToolContext) -> None:
    """Test add_research_question and list_research_questions tools."""
    mock_neo4j = AsyncMock()
    mock_neo4j.create_research_question = AsyncMock(return_value={"question_id": "rq-1", "text": "New Question"})
    mock_neo4j.get_research_questions = AsyncMock(return_value=[{"question_id": "rq-1", "text": "New Question"}])

    mock_emb = AsyncMock()
    mock_emb.embed_query = AsyncMock(return_value=[0.1] * 768)

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_emb = getattr(ServiceRegistry, "_embedding_provider", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._embedding_provider = mock_emb
    ServiceRegistry._initialized = True

    try:
        add_res = await add_research_question(question_text="New Question", tool_context=mock_tool_context)
        assert add_res["status"] == "created"
        assert add_res["question_id"] == "rq-1"

        list_res = await list_research_questions(tool_context=mock_tool_context)
        assert list_res["total"] == 1
        assert list_res["questions"][0]["text"] == "New Question"
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        if old_emb is not None:
            ServiceRegistry._embedding_provider = old_emb
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_export_citation_graph_success(mock_tool_context: ToolContext, tmp_path: Path) -> None:
    """Test export_citation_graph queries Neo4j and exports JSON + GraphML correctly."""
    mock_nodes = [
        {"doi": "10.1016/j.cag.2026.01", "title": "Paper One", "year": 2026, "cited_by_count": 15},
        {"doi": "10.1016/j.cag.2026.02", "title": "Paper Two", "year": 2026, "cited_by_count": 3},
    ]
    mock_edges = [
        {"source": "10.1016/j.cag.2026.01", "target": "10.1016/j.cag.2026.02"},
    ]

    mock_neo4j = AsyncMock()
    mock_neo4j.get_citation_graph_nodes.return_value = mock_nodes
    mock_neo4j.get_citation_graph_edges.return_value = mock_edges

    mock_log = AsyncMock()

    from features.export.service import ExportService
    export_service = ExportService(
        neo4j=mock_neo4j,
        log_service=mock_log,
        projects_dir=str(tmp_path),
    )

    old_export = getattr(ServiceRegistry, "_export_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._export_service = export_service
    ServiceRegistry._initialized = True

    try:
        result = await export_citation_graph(tool_context=mock_tool_context)

        assert result["node_count"] == 2
        assert result["edge_count"] == 1

        json_path = Path(result["json_path"])
        graphml_path = Path(result["graphml_path"])

        assert json_path.exists()
        assert graphml_path.exists()

        exported_json = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(exported_json["nodes"]) == 2
        assert exported_json["nodes"][0]["title"] == "Paper One"
        assert exported_json["links"][0]["source"] == "10.1016/j.cag.2026.01"

        exported_xml = graphml_path.read_text(encoding="utf-8")
        assert "<graphml xmlns=" in exported_xml
        assert '<edge id="e0" source="10.1016/j.cag.2026.01" target="10.1016/j.cag.2026.02"/>' in exported_xml
    finally:
        if old_export is not None:
            ServiceRegistry._export_service = old_export
        else:
            try:
                delattr(ServiceRegistry, "_export_service")
            except AttributeError:
                pass
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_create_new_project_success() -> None:
    """Test create_new_project creates and activates a project successfully."""
    from agents.orchestrator.project_tools import create_new_project
    from projects.models import ProjectResponse

    mock_project = ProjectResponse(
        id="proj-111",
        name="Bread Making",
        topic="baking techniques",
        description="Literature review on baking techniques",
        status="active",
    )

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    mock_neo4j = AsyncMock()
    mock_mysql = AsyncMock()
    mock_log = MagicMock()
    mock_log._mysql = mock_mysql

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_log = getattr(ServiceRegistry, "_log_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._log_service = mock_log
    ServiceRegistry._initialized = True

    try:
        with patch("projects.service.create_project", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_project

            result = await create_new_project(
                name="Bread Making",
                topic="baking techniques",
                tool_context=mock_ctx,
            )

            assert result["status"] == "created"
            assert result["project_id"] == "proj-111"
            assert result["name"] == "Bread Making"
            assert mock_ctx.state["project_id"] == "proj-111"
            mock_create.assert_called_once()
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            delattr(ServiceRegistry, "_neo4j")
        if old_log is not None:
            ServiceRegistry._log_service = old_log
        else:
            delattr(ServiceRegistry, "_log_service")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_select_project_success() -> None:
    """Test select_project activates an existing project successfully."""
    from agents.orchestrator.project_tools import select_project
    from projects.models import ProjectResponse

    mock_project = ProjectResponse(
        id="proj-222",
        name="Bread Fermentation",
        topic="fermentation",
        description="Literature review on fermentation",
        status="active",
    )

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    mock_mysql = AsyncMock()
    mock_log = MagicMock()
    mock_log._mysql = mock_mysql

    old_log = getattr(ServiceRegistry, "_log_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._log_service = mock_log
    ServiceRegistry._initialized = True

    try:
        with patch("projects.service.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_project

            result = await select_project(
                project_id="proj-222",
                tool_context=mock_ctx,
            )

            assert result["status"] == "activated"
            assert result["project_id"] == "proj-222"
            assert mock_ctx.state["project_id"] == "proj-222"
            mock_get.assert_called_once_with("proj-222", mock_mysql)
    finally:
        if old_log is not None:
            ServiceRegistry._log_service = old_log
        else:
            delattr(ServiceRegistry, "_log_service")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_list_projects_success() -> None:
    """Test list_projects returns a list of projects successfully."""
    from agents.orchestrator.project_tools import list_projects
    from projects.models import ProjectResponse

    mock_projects = [
        ProjectResponse(
            id="proj-1",
            name="P1",
            topic="T1",
            description="D1",
            status="active",
        ),
        ProjectResponse(
            id="proj-2",
            name="P2",
            topic="T2",
            description="D2",
            status="active",
        ),
    ]

    mock_neo4j = AsyncMock()
    mock_mysql = AsyncMock()
    mock_log = MagicMock()
    mock_log._mysql = mock_mysql

    old_log = getattr(ServiceRegistry, "_log_service", None)
    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._log_service = mock_log
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        with patch("projects.service.get_projects", new_callable=AsyncMock) as mock_get_all:
            mock_get_all.return_value = mock_projects

            result = await list_projects()

            assert result["total"] == 2
            assert len(result["projects"]) == 2
            assert result["projects"][0]["project_id"] == "proj-1"
            assert result["projects"][1]["name"] == "P2"
            mock_get_all.assert_called_once_with(neo4j=mock_neo4j, include_archived=False)
    finally:
        if old_log is not None:
            ServiceRegistry._log_service = old_log
        else:
            if hasattr(ServiceRegistry, "_log_service"):
                delattr(ServiceRegistry, "_log_service")
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            if hasattr(ServiceRegistry, "_neo4j"):
                delattr(ServiceRegistry, "_neo4j")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_run_graphselect_traversal_tool_bounded_one_hop_success(
    mock_tool_context: ToolContext,
) -> None:
    """Verify run_graphselect_traversal tool executes 1-hop expansion and returns rich candidates."""
    from features.search.models import CandidatePaperState, OneHopExpansionResult

    mock_candidates = [
        CandidatePaperState(
            doi="10.1000/cand1",
            title="Candidate 1",
            authors=["Alice"],
            year=2024,
            venue="ICLR",
            abstract_snippet="Abstract snippet 1",
            direction="forward_citation",
            citation_count=50,
            in_graph_degree=2,
            similarity_scores=[{"question_id": "rq-1", "question": "Q1", "score": 0.92}],
            max_similarity=0.92,
            mean_similarity=0.92,
            already_in_library=False,
            embedding_cached=True,
            pagerank_score=0.8,
        ),
        CandidatePaperState(
            doi="10.1000/cand2",
            title="Candidate 2",
            authors=["Bob"],
            year=2023,
            venue="NeurIPS",
            abstract_snippet="Abstract snippet 2",
            direction="backward_reference",
            citation_count=120,
            in_graph_degree=1,
            similarity_scores=[{"question_id": "rq-1", "question": "Q1", "score": 0.85}],
            max_similarity=0.85,
            mean_similarity=0.85,
            already_in_library=True,
            embedding_cached=True,
            pagerank_score=0.5,
        ),
    ]

    mock_result = OneHopExpansionResult(
        seed_doi="10.1145/3292500.3330919",
        seed_title="Seed Paper",
        cycle_level=1,
        total_discovered=2,
        total_new=2,
        forward_count=1,
        backward_count=1,
        both_count=0,
        candidates=mock_candidates,
        new_dois=["10.1000/cand1", "10.1000/cand2"],
        traversal_summary=["1-Hop GraphSelect traversal complete."],
        errors=[],
    )

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion.return_value = mock_result

    old_crawler = getattr(ServiceRegistry, "_crawler_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._crawler_service = mock_crawler
    ServiceRegistry._initialized = True

    try:
        result = await run_graphselect_traversal(
            seed_doi="10.1145/3292500.3330919",
            max_depth=1,
            similarity_threshold=0.6,
            mode="interactive",
            tool_context=mock_tool_context,
        )

        assert result["status"] == "completed"
        assert result["seed_doi"] == "10.1145/3292500.3330919"
        assert result["cycle_level"] == 1
        assert result["total_discovered"] == 2
        assert len(result["candidates"]) == 2

        candidates: list[dict[str, Any]] = result["candidates"]  # type: ignore[assignment]
        for cand in candidates:
            assert "doi" in cand
            assert "title" in cand
            assert "authors" in cand
            assert "year" in cand
            assert "venue" in cand
            assert "abstract_snippet" in cand
            assert "direction" in cand
            assert "citation_count" in cand
            assert "in_graph_degree" in cand
            assert "similarity_scores" in cand
            assert "already_in_library" in cand

        mock_crawler.run_one_hop_expansion.assert_called_once_with(
            session_id="project-123",
            seed_doi="10.1145/3292500.3330919",
            project_id="project-123",
            embedding_provider=getattr(ServiceRegistry, "embedding_provider", None),
        )
    finally:
        if old_crawler is not None:
            ServiceRegistry._crawler_service = old_crawler
        else:
            if hasattr(ServiceRegistry, "_crawler_service"):
                delattr(ServiceRegistry, "_crawler_service")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_run_graphselect_traversal_tool_clamps_depth_to_one_in_interactive_mode(
    mock_tool_context: ToolContext,
) -> None:
    """In interactive HITL mode, tool enforces 1-hop execution even if max_depth > 1."""
    from features.search.models import OneHopExpansionResult

    mock_result = OneHopExpansionResult(
        seed_doi="10.1145/3292500.3330919",
        seed_title="Seed Paper",
        cycle_level=1,
        total_discovered=0,
        total_new=0,
        forward_count=0,
        backward_count=0,
        both_count=0,
        candidates=[],
        new_dois=[],
        traversal_summary=["Completed."],
        errors=[],
    )

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion.return_value = mock_result

    old_crawler = getattr(ServiceRegistry, "_crawler_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._crawler_service = mock_crawler
    ServiceRegistry._initialized = True

    try:
        result = await run_graphselect_traversal(
            seed_doi="10.1145/3292500.3330919",
            max_depth=3,
            mode="interactive",
            tool_context=mock_tool_context,
        )

        assert result["status"] == "completed"
        assert result["max_depth"] == 1
        mock_crawler.run_one_hop_expansion.assert_called_once()
    finally:
        if old_crawler is not None:
            ServiceRegistry._crawler_service = old_crawler
        else:
            if hasattr(ServiceRegistry, "_crawler_service"):
                delattr(ServiceRegistry, "_crawler_service")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_run_graphselect_traversal_missing_project_id_returns_error() -> None:
    """Tool fails cleanly with descriptive error if project_id is missing."""
    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    result = await run_graphselect_traversal(
        seed_doi="10.1145/3292500.3330919",
        tool_context=mock_ctx,
    )

    assert "error" in result
    assert "No project_id in session state" in str(result["error"])


@pytest.mark.asyncio
async def test_run_graphselect_traversal_auto_lookup_seed_from_project_library(
    mock_tool_context: ToolContext,
) -> None:
    """If seed_doi is omitted, tool queries Neo4j for an existing project paper."""
    from features.search.models import OneHopExpansionResult

    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = [{"doi": "10.1000/library_seed"}]

    mock_result = OneHopExpansionResult(
        seed_doi="10.1000/library_seed",
        seed_title="Library Seed",
        cycle_level=1,
        total_discovered=1,
        total_new=1,
        forward_count=1,
        backward_count=0,
        both_count=0,
        candidates=[],
        new_dois=["10.1000/c1"],
        traversal_summary=[],
        errors=[],
    )

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion.return_value = mock_result

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_crawler = getattr(ServiceRegistry, "_crawler_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._crawler_service = mock_crawler
    ServiceRegistry._initialized = True

    try:
        result = await run_graphselect_traversal(
            seed_doi="",
            tool_context=mock_tool_context,
        )

        assert result["status"] == "completed"
        assert result["seed_doi"] == "10.1000/library_seed"
        mock_crawler.run_one_hop_expansion.assert_called_once_with(
            session_id="project-123",
            seed_doi="10.1000/library_seed",
            project_id="project-123",
            embedding_provider=getattr(ServiceRegistry, "embedding_provider", None),
        )
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            if hasattr(ServiceRegistry, "_neo4j"):
                delattr(ServiceRegistry, "_neo4j")
        if old_crawler is not None:
            ServiceRegistry._crawler_service = old_crawler
        else:
            if hasattr(ServiceRegistry, "_crawler_service"):
                delattr(ServiceRegistry, "_crawler_service")
        ServiceRegistry._initialized = old_init


@pytest.mark.asyncio
async def test_run_graphselect_traversal_no_seed_found_returns_error(
    mock_tool_context: ToolContext,
) -> None:
    """Tool returns descriptive error if seed_doi is omitted and project has no papers."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers.return_value = []

    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        result = await run_graphselect_traversal(
            seed_doi="",
            tool_context=mock_tool_context,
        )

        assert "error" in result
        assert "seed_doi is required" in str(result["error"])
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            if hasattr(ServiceRegistry, "_neo4j"):
                delattr(ServiceRegistry, "_neo4j")
        ServiceRegistry._initialized = old_init


def test_stage0_and_stage1_dialectical_agents() -> None:
    """Verify Stage 0 and 1 Dialectical Agent pairs and workflows."""
    from agents.stage0_guidance import (
        ParentResearchAdvisor,
        IntentAlignmentCritic,
        stage0_guidance_workflow,
    )
    from agents.stage1_scoping import (
        SocraticScopingAdvisor,
        ScopeBoundariesCritic,
        stage1_scoping_workflow,
    )

    p_adv = ParentResearchAdvisor()
    assert p_adv.name == "ParentResearchAdvisor"
    assert len(p_adv.tools) >= 2
    i_crit = IntentAlignmentCritic()
    assert i_crit.name == "IntentAlignmentCritic"
    assert len(stage0_guidance_workflow.sub_agents) == 2

    s_adv = SocraticScopingAdvisor()
    assert s_adv.name == "SocraticScopingAdvisor"
    s_crit = ScopeBoundariesCritic()
    assert s_crit.name == "ScopeBoundariesCritic"
    assert len(stage1_scoping_workflow.sub_agents) == 2


def test_stage2_and_stage3_dialectical_agents() -> None:
    """Verify Stage 2 and 3 Dialectical Agent pairs and workflows."""
    from agents.stage2_acquisition import (
        SearchSnowballAgent,
        RelevanceQualityAuditor,
        stage2_acquisition_workflow,
    )
    from agents.stage3_extraction import (
        MultimodalVisionExtractor,
        EvidenceProvenanceAuditor,
        stage3_extraction_workflow,
    )

    s_agent = SearchSnowballAgent()
    assert s_agent.name == "SearchSnowballAgent"
    r_aud = RelevanceQualityAuditor()
    assert r_aud.name == "RelevanceQualityAuditor"
    assert len(stage2_acquisition_workflow.sub_agents) == 2

    m_agent = MultimodalVisionExtractor()
    assert m_agent.name == "MultimodalVisionExtractor"
    e_aud = EvidenceProvenanceAuditor()
    assert e_aud.name == "EvidenceProvenanceAuditor"
    assert len(stage3_extraction_workflow.sub_agents) == 2


def test_stage4_and_stage5_dialectical_agents() -> None:
    """Verify Stage 4 and 5 Dialectical Agent pairs and workflows."""
    from agents.stage4_synthesis import (
        MethodologyArchitect,
        NoveltyRigorChallenger,
        stage4_synthesis_workflow,
    )
    from agents.stage5_drafting import (
        GroundedSynthesisWriter,
        AcademicRedTeamer,
        stage5_drafting_workflow,
    )

    m_arch = MethodologyArchitect()
    assert m_arch.name == "MethodologyArchitect"
    n_chall = NoveltyRigorChallenger()
    assert n_chall.name == "NoveltyRigorChallenger"
    assert len(stage4_synthesis_workflow.sub_agents) == 2

    g_writer = GroundedSynthesisWriter()
    assert g_writer.name == "GroundedSynthesisWriter"
    a_rt = AcademicRedTeamer()
    assert a_rt.name == "AcademicRedTeamer"
    assert len(stage5_drafting_workflow.sub_agents) == 2


