"""Agent Swarm service for dynamic introspection, tool schema reflection, and hot-reloading."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, get_type_hints

from config import get_settings
from features.agents.models import (
    AgentConfig,
    AgentConfigUpdate,
    AgentMetadata,
    AgentRegistryResponse,
    AgentResetResponse,
    AgentSettingsUpdateResponse,
    AgentToolDefinition,
    LiveAgentTrace,
    ToolCallTrace,
    ToolParameterProperty,
    ToolParameterSchema,
)

logger = logging.getLogger(__name__)

# Known architectural metadata for agents to enrich introspection
AGENT_DISPLAY_ROLES: dict[str, dict[str, str]] = {
    "ProjectAgent": {
        "display_name": "Project Orchestrator",
        "role": "Root Orchestrator",
        "tier": "tier1",
    },
    "ResearchAgent": {
        "display_name": "Research Coordinator",
        "role": "Research Coordinator",
        "tier": "tier1",
    },
    "ALRSAgent": {
        "display_name": "Literature Discovery Agent",
        "role": "Paper Discovery & GraphSelect BFS Traversal",
        "tier": "tier2",
    },
    "GapFinderAgent": {
        "display_name": "Gap Analysis & Ranking Agent",
        "role": "Citation Analysis, Coverage Gaps & PageRank Ranking",
        "tier": "tier2",
    },
    "EvidenceSynthesizerAgent": {
        "display_name": "Evidence Synthesizer Agent",
        "role": "Literature Extraction & Comparison Matrix Synthesis",
        "tier": "tier2",
    },
    "PlannerAgent": {
        "display_name": "Outline Planner Agent",
        "role": "Outline Architecture & Section Scoping",
        "tier": "tier1",
    },
    "DraftingAgent": {
        "display_name": "Section Drafting Agent",
        "role": "Academic Literature Review Drafting",
        "tier": "tier2",
    },
    "ReviewerAgent": {
        "display_name": "Peer Review Agent",
        "role": "Peer Review, Rubric Critique & Citation Verification",
        "tier": "tier1",
    },
    "DebuggerAgent": {
        "display_name": "Autonomous Diagnostic Agent",
        "role": "Runtime Error Interception & AST Hot-Patching",
        "tier": "tier1",
    },
}

# Python type to JSON Schema type mapping
TYPE_MAPPING: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def python_type_to_json_schema(py_type: Any) -> str:
    """Convert Python type annotations to JSON Schema type strings."""
    if py_type in TYPE_MAPPING:
        return TYPE_MAPPING[py_type]
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        if origin in (list, tuple, set):
            return "array"
        if origin is dict:
            return "object"
        if origin is type(None):
            return "null"
        # If Union/Optional
        args = getattr(py_type, "__args__", ())
        for arg in args:
            if arg is not type(None):
                res = python_type_to_json_schema(arg)
                if res != "null":
                    return res

    # Check string representations for unions or optional types (order: check array/dict first)
    type_str = str(py_type).lower()
    if "list" in type_str or "array" in type_str or "tuple" in type_str or "set" in type_str:
        return "array"
    if "dict" in type_str or "mapping" in type_str:
        return "object"
    if "bool" in type_str:
        return "boolean"
    if "float" in type_str or "double" in type_str:
        return "number"
    if "int" in type_str:
        return "integer"
    if "str" in type_str:
        return "string"
    return "string"


def extract_tool_schema(tool: Any) -> AgentToolDefinition:
    """Dynamically extract tool name, docstring, and JSON argument schema."""
    tool_name = getattr(tool, "__name__", getattr(tool, "name", str(tool)))
    docstring = inspect.getdoc(tool) or getattr(tool, "description", "") or ""
    
    properties: dict[str, Any] = {}
    required: list[str] = []

    # If it's a callable function
    fn = getattr(tool, "fn", tool) if hasattr(tool, "fn") else tool
    if callable(fn):
        try:
            sig = inspect.signature(fn)
            type_hints = {}
            try:
                type_hints = get_type_hints(fn)
            except Exception:
                pass

            for param_name, param in sig.parameters.items():
                # Skip internal injected parameters like tool_context
                if param_name in ("tool_context", "context", "self", "cls"):
                    continue

                param_type = type_hints.get(param_name, param.annotation)
                json_type = python_type_to_json_schema(param_type) if param_type is not inspect.Parameter.empty else "string"

                prop_def: dict[str, Any] = {"type": json_type}
                if param.default is not inspect.Parameter.empty:
                    prop_def["default"] = param.default
                else:
                    required.append(param_name)

                properties[param_name] = prop_def
        except Exception as exc:
            logger.debug("Failed to inspect signature for tool %s: %s", tool_name, exc)

    return AgentToolDefinition(
        name=tool_name,
        description=docstring,
        parameters=ToolParameterSchema(
            type="object",
            properties=properties,
            required=required,
        ),
    )


class AgentService:
    """Service managing dynamic agent introspection, hot-reloading, and settings persistence."""

    def __init__(self, root_agent: Any, mysql_service: Any = None) -> None:
        self.root_agent = root_agent
        self.mysql = mysql_service
        self._canonical_defaults: dict[str, dict[str, Any]] = {}
        self._active_overrides: dict[str, dict[str, Any]] = {}
        self._initialized = False
        self._capture_canonical_defaults()

    def _get_all_agents(self) -> list[Any]:
        """Traverse the entire agent hierarchy dynamically and return unique agent instances."""
        agents_list = []
        visited_ids = set()

        def _traverse(current: Any):
            if current is None or id(current) in visited_ids:
                return
            visited_ids.add(id(current))
            
            name = getattr(current, "name", None)
            # Only include agents that are swarm agents with models (filtering out loop/control wrappers)
            if name and hasattr(current, "model") and name in AGENT_DISPLAY_ROLES:
                agents_list.append(current)

            sub_agents = getattr(current, "sub_agents", []) or []
            for sub in sub_agents:
                _traverse(sub)

        _traverse(self.root_agent)
        return agents_list

    def _capture_canonical_defaults(self) -> None:
        """Capture factory defaults for every agent at initialization."""
        settings = get_settings()
        default_tier1 = getattr(settings, "adk_tier1_model", settings.adk_model_name)
        default_tier2 = getattr(settings, "adk_tier2_model", settings.adk_model_name)

        agents = self._get_all_agents()
        for agent in agents:
            name = getattr(agent, "name", "UnnamedAgent")
            meta = AGENT_DISPLAY_ROLES.get(name, {})
            tier = meta.get("tier", "tier2")
            default_model = getattr(agent, "model", default_tier1 if tier == "tier1" else default_tier2)
            
            # Canonical temperature based on agent role
            if tier == "tier1":
                default_temp = 0.70
                default_top_p = 0.95
                default_tokens = 8192
            else:
                default_temp = 0.20 if "ALRS" in name or "Search" in name else 0.40
                default_top_p = 0.90
                default_tokens = 8192

            base_instruction = getattr(agent, "instruction", "") or ""
            if callable(base_instruction):
                try:
                    base_instruction = base_instruction()
                except Exception:
                    base_instruction = str(base_instruction)

            self._canonical_defaults[name] = {
                "default_model": default_model,
                "default_temperature": default_temp,
                "default_top_p": default_top_p,
                "default_max_output_tokens": default_tokens,
                "system_prompt": str(base_instruction),
            }

    async def initialize_from_db(self) -> None:
        """Load persisted agent overrides from MySQL settings table if available."""
        if self._initialized:
            return
        if self.mysql is not None:
            try:
                row = await asyncio.wait_for(
                    self.mysql.fetch_one(
                        "SELECT setting_value FROM settings WHERE setting_key = 'agent_swarm_overrides'"
                    ),
                    timeout=2.0
                )
                if row and row.get("setting_value"):
                    saved_overrides = json.loads(row["setting_value"])
                    if isinstance(saved_overrides, dict):
                        self._active_overrides.update(saved_overrides)
                        self._apply_overrides_to_live_agents()
            except Exception as exc:
                logger.warning("Failed to load agent overrides from MySQL: %s", exc)
        self._initialized = True

    def _apply_overrides_to_live_agents(self) -> None:
        """Apply active in-memory overrides directly onto live ADK agent instances."""
        agents = self._get_all_agents()
        for agent in agents:
            name = getattr(agent, "name", "")
            if not hasattr(agent, "model"):
                continue
            canonical = self._canonical_defaults.get(name, {})
            override = self._active_overrides.get(name)

            if override:
                # Update model if provided
                if override.get("model") and hasattr(agent, "model"):
                    agent.model = override["model"]
                elif canonical.get("default_model") and hasattr(agent, "model"):
                    agent.model = canonical["default_model"]

                # Update instruction with custom prefix if provided
                prefix = override.get("custom_prompt_prefix")
                base_instruction = canonical.get("system_prompt", "")
                if hasattr(agent, "instruction"):
                    if prefix:
                        agent.instruction = f"{prefix.strip()}\n\n{base_instruction}"
                    else:
                        agent.instruction = base_instruction
            else:
                # Restore canonical defaults
                if canonical.get("default_model") and hasattr(agent, "model"):
                    agent.model = canonical["default_model"]
                if hasattr(agent, "instruction"):
                    agent.instruction = canonical.get("system_prompt", "")

    async def get_registry(self) -> AgentRegistryResponse:
        """Dynamically introspect and return metadata for all agents in the swarm."""
        await self.initialize_from_db()
        settings = get_settings()
        default_tier1 = getattr(settings, "adk_tier1_model", settings.adk_model_name)
        default_tier2 = getattr(settings, "adk_tier2_model", settings.adk_model_name)

        agents = self._get_all_agents()
        agent_metas: list[AgentMetadata] = []

        for agent in agents:
            name = getattr(agent, "name", "UnnamedAgent")
            description = getattr(agent, "description", "") or ""
            meta_info = AGENT_DISPLAY_ROLES.get(name, {})
            display_name = meta_info.get("display_name", name)
            role = meta_info.get("role", "Specialized Agent")
            tier = meta_info.get("tier", "tier2")

            # Discover sub-agents (unpacking intermediate wrappers like WriterAgent/LoopAgent)
            sub_agent_names: list[str] = []
            for sub in getattr(agent, "sub_agents", []) or []:
                sub_name = getattr(sub, "name", None)
                if sub_name == "WriterAgent":
                    for w_sub in getattr(sub, "sub_agents", []) or []:
                        if getattr(w_sub, "name", None) == "WriterReviewerLoop":
                            for loop_sub in getattr(w_sub, "sub_agents", []) or []:
                                ls_name = getattr(loop_sub, "name", None)
                                if ls_name:
                                    sub_agent_names.append(ls_name)
                        elif getattr(w_sub, "name", None):
                            sub_agent_names.append(w_sub.name)
                elif sub_name == "WriterReviewerLoop":
                    for loop_sub in getattr(sub, "sub_agents", []) or []:
                        ls_name = getattr(loop_sub, "name", None)
                        if ls_name:
                            sub_agent_names.append(ls_name)
                elif sub_name:
                    sub_agent_names.append(sub_name)

            # Discover tools and schemas
            tool_definitions: list[AgentToolDefinition] = []
            for tool in getattr(agent, "tools", []) or []:
                tool_definitions.append(extract_tool_schema(tool))

            canonical = self._canonical_defaults.get(name, {
                "default_model": default_tier1 if tier == "tier1" else default_tier2,
                "default_temperature": 0.7 if tier == "tier1" else 0.3,
                "default_top_p": 0.95,
                "default_max_output_tokens": 8192,
                "system_prompt": getattr(agent, "instruction", "") or "",
            })

            override = self._active_overrides.get(name, {})
            
            active_model = override.get("model") or getattr(agent, "model", canonical["default_model"])
            active_temp = override.get("temperature", canonical["default_temperature"])
            active_top_p = override.get("top_p", canonical["default_top_p"])
            active_tokens = override.get("max_output_tokens", canonical["default_max_output_tokens"])
            custom_prefix = override.get("custom_prompt_prefix", None)

            is_default = (
                active_model == canonical["default_model"]
                and abs(active_temp - canonical["default_temperature"]) < 1e-4
                and abs(active_top_p - canonical["default_top_p"]) < 1e-4
                and active_tokens == canonical["default_max_output_tokens"]
                and not custom_prefix
            )

            config = AgentConfig(
                model=active_model,
                default_model=canonical["default_model"],
                temperature=active_temp,
                default_temperature=canonical["default_temperature"],
                top_p=active_top_p,
                default_top_p=canonical["default_top_p"],
                max_output_tokens=active_tokens,
                default_max_output_tokens=canonical["default_max_output_tokens"],
                custom_prompt_prefix=custom_prefix,
                system_prompt=canonical["system_prompt"],
                is_default=is_default,
            )

            agent_metas.append(
                AgentMetadata(
                    name=name,
                    display_name=display_name,
                    description=description,
                    role=role,
                    tier=tier,
                    sub_agents=sub_agent_names,
                    tools=tool_definitions,
                    config=config,
                )
            )

        return AgentRegistryResponse(
            agents=agent_metas,
            total=len(agent_metas),
            system_default_tier1_model=default_tier1,
            system_default_tier2_model=default_tier2,
        )

    async def update_settings(self, updates: dict[str, AgentConfigUpdate]) -> AgentSettingsUpdateResponse:
        """Persist customized configuration parameters and hot-reload live ADK agent instances."""
        await self.initialize_from_db()
        all_agent_names = {getattr(a, "name", "") for a in self._get_all_agents()}
        
        updated: list[str] = []
        for agent_name, update in updates.items():
            if agent_name not in all_agent_names:
                continue

            current_override = self._active_overrides.get(agent_name, {})
            dumped = update.model_dump(exclude_none=True)
            current_override.update(dumped)
            self._active_overrides[agent_name] = current_override
            updated.append(agent_name)

        # Apply immediately to live agent instances
        self._apply_overrides_to_live_agents()

        # Persist to database if available
        if self.mysql is not None:
            try:
                await asyncio.wait_for(
                    self.mysql.execute(
                        """INSERT INTO settings (setting_key, setting_value)
                           VALUES ('agent_swarm_overrides', %s)
                           ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)""",
                        (json.dumps(self._active_overrides),)
                    ),
                    timeout=2.0
                )
            except Exception as exc:
                logger.warning("Failed to persist agent swarm overrides to MySQL: %s", exc)

        return AgentSettingsUpdateResponse(
            success=True,
            message=f"Successfully hot-reloaded configuration for {len(updated)} agent(s).",
            updated_agents=updated,
        )

    async def reset_settings(self, agent_name: Optional[str] = None) -> AgentResetResponse:
        """Reset single or all agent configurations back to factory defaults."""
        await self.initialize_from_db()
        all_agent_names = [getattr(a, "name", "") for a in self._get_all_agents()]

        reset_agents: list[str] = []
        if agent_name:
            if agent_name in self._active_overrides:
                del self._active_overrides[agent_name]
            reset_agents.append(agent_name)
        else:
            self._active_overrides.clear()
            reset_agents.extend(all_agent_names)

        # Apply reset to live instances
        self._apply_overrides_to_live_agents()

        # Persist reset to database
        if self.mysql is not None:
            try:
                await asyncio.wait_for(
                    self.mysql.execute(
                        """INSERT INTO settings (setting_key, setting_value)
                           VALUES ('agent_swarm_overrides', %s)
                           ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)""",
                        (json.dumps(self._active_overrides),)
                    ),
                    timeout=2.0
                )
            except Exception as exc:
                logger.warning("Failed to persist reset settings to MySQL: %s", exc)

        return AgentResetResponse(
            success=True,
            message=f"Successfully reset configuration to system defaults for {len(reset_agents)} agent(s).",
            reset_agents=reset_agents,
        )

    async def get_traces(
        self,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[LiveAgentTrace]:
        """Query execution traces from agent_traces and format for inspector pane."""
        traces: list[LiveAgentTrace] = []
        if self.mysql is None:
            return traces

        try:
            conditions = []
            args: list[Any] = []

            if agent_name:
                conditions.append("agent_name = %s")
                args.append(agent_name)
            if project_id:
                conditions.append("project_id = %s")
                args.append(project_id)
            if since:
                since_utc = since.astimezone(timezone.utc) if since.tzinfo is not None else since
                conditions.append("created_at >= %s")
                args.append(since_utc.strftime("%Y-%m-%d %H:%M:%S"))

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"SELECT * FROM agent_traces WHERE {where_clause} ORDER BY created_at DESC LIMIT %s"
            args.append(limit)

            rows = await asyncio.wait_for(
                self.mysql.fetch_all(query, tuple(args)),
                timeout=2.0
            )
            for row in rows:
                details = {}
                if row.get("details"):
                    try:
                        details = json.loads(row["details"]) if isinstance(row["details"], str) else row["details"]
                    except Exception:
                        details = {}

                # Format tool calls
                tool_calls: list[ToolCallTrace] = []
                if details.get("tool_name"):
                    tool_calls.append(
                        ToolCallTrace(
                            name=details["tool_name"],
                            arguments=details.get("args", {}),
                            result=str(details.get("result", "")),
                        )
                    )

                created_at_dt = row.get("created_at")
                timestamp_str = (
                    created_at_dt.isoformat() if isinstance(created_at_dt, datetime) else str(created_at_dt)
                )

                traces.append(
                    LiveAgentTrace(
                        id=str(row.get("id", "")),
                        timestamp=timestamp_str,
                        project_id=row.get("project_id"),
                        agent_name=row.get("agent_name", "UnknownAgent"),
                        action_summary=f"Event: {row.get('event_type', 'llm_call')}",
                        llm_prompt=details.get("prompt") or details.get("prompt_payload"),
                        llm_response=details.get("response") or details.get("raw_response"),
                        tool_calls=tool_calls,
                        token_count=row.get("token_count", 0),
                        latency_ms=details.get("latency_ms"),
                        status="error" if row.get("event_type") == "error" else "success",
                        decision_outcome=details.get("decision_outcome"),
                    )
                )
        except Exception as exc:
            logger.warning("Failed to query agent traces from MySQL: %s", exc)

        return traces
