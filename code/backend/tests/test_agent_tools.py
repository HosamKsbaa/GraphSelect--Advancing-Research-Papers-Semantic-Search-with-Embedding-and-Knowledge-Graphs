"""Unit tests for the new agent tools: get_top_authors, get_top_venues, and export_citation_graph."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.tools.search_tools import get_top_authors, get_top_venues
from agents.writing.tools.export_tools import export_citation_graph


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

    # Temporarily override ServiceRegistry._neo4j and mark initialized
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

        # Verify correct Cypher query execution
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

    # Create a real ExportService with mocked dependencies
    from features.export.service import ExportService
    export_service = ExportService(
        neo4j=mock_neo4j,
        log_service=mock_log,
        projects_dir=str(tmp_path),
    )

    # Stub registry
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

        # Verify exported JSON schema
        exported_json = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(exported_json["nodes"]) == 2
        assert exported_json["nodes"][0]["title"] == "Paper One"
        assert exported_json["links"][0]["source"] == "10.1016/j.cag.2026.01"

        # Verify exported GraphML schema
        exported_xml = graphml_path.read_text(encoding="utf-8")
        assert "<graphml xmlns=" in exported_xml
        assert '<edge id="e0" source="10.1016/j.cag.2026.01" target="10.1016/j.cag.2026.02"/>' in exported_xml

        # Check logging trace
        mock_log.log_agent_trace.assert_called_once()
        trace_call = mock_log.log_agent_trace.call_args[1]
        assert trace_call["project_id"] == "project-123"
        assert trace_call["agent_name"] == "WriterAgent"
        assert trace_call["details"]["tool"] == "export_citation_graph"
        assert trace_call["details"]["node_count"] == 2
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

    # Mock the tool context
    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    # Mock services in registry
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

    # Mock the tool context
    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    # Mock services in registry
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

    # Mock services in registry
    mock_mysql = AsyncMock()
    mock_log = MagicMock()
    mock_log._mysql = mock_mysql

    old_log = getattr(ServiceRegistry, "_log_service", None)
    old_init = ServiceRegistry._initialized

    ServiceRegistry._log_service = mock_log
    ServiceRegistry._initialized = True

    try:
        with patch("projects.service.get_projects", new_callable=AsyncMock) as mock_get_all:
            mock_get_all.return_value = mock_projects

            result = await list_projects()

            assert result["total"] == 2
            assert len(result["projects"]) == 2
            assert result["projects"][0]["project_id"] == "proj-1"
            assert result["projects"][1]["name"] == "P2"
            mock_get_all.assert_called_once_with(mock_mysql, include_archived=False)
    finally:
        if old_log is not None:
            ServiceRegistry._log_service = old_log
        else:
            delattr(ServiceRegistry, "_log_service")
        ServiceRegistry._initialized = old_init

