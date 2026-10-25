"""MCP Server adapter & JSON-RPC `/mcp` endpoint for the ALRS Research Agent (M3).

Exposes the same plain Python functions (`search_papers`, `discover_literature`,
`get_collection`, `write_review`, `verify_citations`, `load_skill`) over both
`mcp.server.fastmcp.FastMCP` and a FastAPI `/mcp` JSON-RPC 2.0 router.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field

from engines.citations import AnalysisFinding

from .skills import list_available_skills
from .tools import AgentToolRuntime, WriteReviewOutput


class McpToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    inputSchema: dict[str, Any]


class McpRpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = "2.0"
    id: int | str | None = 1
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class McpServerAdapter:
    """Thin MCP protocol wrapper around `AgentToolRuntime`."""

    def __init__(self, runtime: AgentToolRuntime) -> None:
        self.runtime = runtime

    def list_tools(self) -> list[McpToolDefinition]:
        return [
            McpToolDefinition(
                name="search_papers",
                description="Search OpenAlex for candidate seed papers with DOIs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            McpToolDefinition(
                name="discover_literature",
                description="Run E-GraphSelect citation discovery from a seed DOI and save a PaperCollection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "seed_doi": {"type": "string"},
                        "research_questions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "max_depth": {"type": "integer", "default": 2},
                        "similarity_threshold": {"type": "number", "default": 0.3},
                    },
                    "required": ["seed_doi", "research_questions"],
                },
            ),
            McpToolDefinition(
                name="get_collection",
                description="Retrieve saved collection papers and exact sentence spans for verified quoting.",
                inputSchema={
                    "type": "object",
                    "properties": {"collection_id": {"type": "string"}},
                    "required": ["collection_id"],
                },
            ),
            McpToolDefinition(
                name="write_review",
                description="Verify findings against saved abstracts and assemble a cited Markdown literature review.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_id": {"type": "string"},
                        "findings": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["collection_id", "findings"],
                },
            ),
            McpToolDefinition(
                name="verify_citations",
                description="Audit a synthesized review against its saved PaperCollection and strip unsupported DOIs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_id": {"type": "string"},
                        "review_output": {"type": "object"},
                    },
                    "required": ["collection_id", "review_output"],
                },
            ),
            McpToolDefinition(
                name="load_skill",
                description="Load an on-demand capability skill (SKILL.md) by name.",
                inputSchema={
                    "type": "object",
                    "properties": {"skill_name": {"type": "string"}},
                    "required": ["skill_name"],
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        if name == "search_papers":
            return await self.runtime.search_papers(
                query=str(arguments["query"]),
                limit=int(arguments.get("limit", 5)),
            )
        if name == "discover_literature":
            raw_questions = arguments.get("research_questions", [])
            questions = [str(q) for q in raw_questions] if isinstance(raw_questions, list) else []
            return await self.runtime.discover_literature(
                seed_doi=str(arguments["seed_doi"]),
                research_questions=questions,
                max_depth=int(arguments.get("max_depth", 2)),
                similarity_threshold=float(arguments.get("similarity_threshold", 0.3)),
            )
        if name == "get_collection":
            return self.runtime.get_collection(collection_id=str(arguments["collection_id"]))
        if name == "write_review":
            raw_findings = arguments.get("findings", [])
            findings = [
                AnalysisFinding.model_validate(item)
                for item in (raw_findings if isinstance(raw_findings, list) else [])
            ]
            return self.runtime.write_review(
                collection_id=str(arguments["collection_id"]),
                findings=findings,
            )
        if name == "verify_citations":
            review_out = WriteReviewOutput.model_validate(arguments["review_output"])
            result = self.runtime.verify_citations(
                collection_id=str(arguments["collection_id"]),
                review_output=review_out,
            )
            assert isinstance(result, BaseModel)
            return result
        if name == "load_skill":
            return self.runtime.load_skill(skill_name=str(arguments["skill_name"]))
        raise KeyError(f"Unknown MCP tool: {name}")

    async def handle_rpc(self, request: McpRpcRequest) -> dict[str, Any]:
        if request.method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "alrs-research-agent", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            }
        if request.method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "tools": [t.model_dump(mode="json") for t in self.list_tools()]
                },
            }
        if request.method == "tools/call":
            tool_name = str(request.params.get("name", ""))
            raw_args = request.params.get("arguments", {})
            args = raw_args if isinstance(raw_args, dict) else {}
            try:
                output = await self.call_tool(tool_name, args)
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {"code": -32000, "message": str(exc)},
                }
            payload = output.model_dump(mode="json")
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "content": [{"type": "text", "text": output.model_dump_json()}],
                    "structuredContent": payload,
                    "isError": False,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": -32601, "message": f"Method not found: {request.method}"},
        }


def build_fastmcp_server(runtime: AgentToolRuntime) -> MCPServer:
    """Create a standard `MCPServer` instance bound to `runtime`."""
    mcp = MCPServer("alrs-research-agent")
    mcp.add_tool(runtime.search_papers, name="search_papers")
    mcp.add_tool(runtime.discover_literature, name="discover_literature")
    mcp.add_tool(runtime.get_collection, name="get_collection")
    mcp.add_tool(runtime.write_review, name="write_review")
    mcp.add_tool(runtime.verify_citations, name="verify_citations")
    mcp.add_tool(runtime.load_skill, name="load_skill")
    return mcp


def create_mcp_router(runtime_getter: Callable[[], AgentToolRuntime]) -> APIRouter:
    """Create a FastAPI router mounted at `/mcp`."""
    router = APIRouter(prefix="/mcp", tags=["mcp"])

    @router.get("/tools")
    async def list_mcp_tools() -> dict[str, Any]:
        adapter = McpServerAdapter(runtime_getter())
        return {
            "tools": [t.model_dump(mode="json") for t in adapter.list_tools()],
            "skills": [s.model_dump(mode="json") for s in list_available_skills()],
        }

    @router.post("")
    async def handle_mcp_rpc(request: McpRpcRequest) -> dict[str, Any]:
        adapter = McpServerAdapter(runtime_getter())
        return await adapter.handle_rpc(request)

    return router
