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
            mock_get_all.assert_called_once_with(mock_mysql, neo4j=mock_neo4j, include_archived=False)
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
