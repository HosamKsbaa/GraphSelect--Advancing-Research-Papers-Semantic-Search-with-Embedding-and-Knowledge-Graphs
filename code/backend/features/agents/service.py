"""Agent Swarm service for dynamic introspection, tool schema reflection, tier management, and hot-reloading."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, get_type_hints

from fastapi import HTTPException, status

from config import get_settings
from features.agents.models import (
    AgentConfig,
    AgentConfigBatchUpdateResponse,
    AgentConfigItem,
    AgentConfigOverrideItem,
    AgentConfigUpdate,
    AgentMetadata,
    AgentRegistryResponse,
    AgentResetResponse,
    AgentSettingsUpdateResponse,
    AgentToolDefinition,
    LiveAgentTrace,
    ModelTier,
    TierCreateRequest,
    TierDeleteResponse,
    TierUpdateRequest,
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
    "WriterAgent": {
        "display_name": "Writing & Export Coordinator",
        "role": "Writing Pipeline, Section Coordination & LaTeX Export",
        "tier": "tier1",
    },
    "DraftingAgent": {
        "display_name": "Section Drafting Agent",
        "role": "Academic Literature Review Drafting",
        "tier": "tier3",
    },
    "ReviewerAgent": {
        "display_name": "Peer Review Agent",
        "role": "Peer Review, Rubric Critique & Citation Verification",
        "tier": "tier3",
    },
    "DebuggerAgent": {
        "display_name": "Autonomous Diagnostic Agent",
        "role": "Runtime Error Interception & AST Hot-Patching",
        "tier": "tier1",
    },
}


def get_agent_display_meta(name: str) -> dict[str, str]:
    """Retrieve metadata for an agent or dynamically infer display name, role, and tier for newly added agents."""
    if name in AGENT_DISPLAY_ROLES:
        return AGENT_DISPLAY_ROLES[name]
    # Dynamically split PascalCase to words: e.g. "DataVisualizerAgent" -> "Data Visualizer Agent"
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", name)
    display = " ".join(words) if words else name
    return {
        "display_name": display,
        "role": f"Autonomous {display}",
        "tier": "tier2",
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
    """Service managing dynamic agent introspection, model tiers, hot-reloading, and settings persistence."""

    def __init__(self, root_agent: Any, neo4j_service: Any = None, mysql_service: Any = None) -> None:
        self.root_agent = root_agent
        self.neo4j = neo4j_service
        self.mysql = mysql_service
        self._tiers: dict[str, ModelTier] = {}
        self._canonical_defaults: dict[str, dict[str, Any]] = {}
        self._active_overrides: dict[str, dict[str, Any]] = {}
        self._initialized = False
        self._init_default_tiers()
        self._capture_canonical_defaults()

    def _init_default_tiers(self) -> None:
        """Initialize the 3 canonical built-in system tiers."""
        settings = get_settings()
        default_tier1 = getattr(settings, "adk_tier1_model", settings.adk_model_name)
        default_tier2 = getattr(settings, "adk_tier2_model", settings.adk_model_name)

        self._tiers = {
            "tier1": ModelTier(
                id="tier1",
                name="Tier 1: Orchestration",
                description="High-rigor coordination, planning, peer review, and runtime diagnosis",
                model=default_tier1,
                temperature=0.70,
                top_p=0.95,
                max_output_tokens=8192,
                color="#3b82f6",
                is_system=True,
            ),
            "tier2": ModelTier(
                id="tier2",
                name="Tier 2: Discovery & Synthesis",
                description="High-throughput literature search, graph traversal, and matrix extraction",
                model=default_tier2,
                temperature=0.30,
                top_p=0.90,
                max_output_tokens=8192,
                color="#10b981",
                is_system=True,
            ),
            "tier3": ModelTier(
                id="tier3",
                name="Tier 3: Writing & Review",
                description="Long-form drafting, rubric critique, and iterative refinement",
                model=default_tier1,
                temperature=0.50,
                top_p=0.95,
                max_output_tokens=8192,
                color="#8b5cf6",
                is_system=True,
            ),
        }

    def _get_all_agents(self) -> list[Any]:
        """Traverse the entire agent hierarchy dynamically and return unique agent instances."""
        agents_list = []
        visited_ids = set()

        def _traverse(current: Any) -> None:
            if current is None or id(current) in visited_ids:
                return
            visited_ids.add(id(current))
            
            name = getattr(current, "name", None)
            # Dynamically include any agent that has a name and a model (LLM agent)
            if name and hasattr(current, "model"):
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
            meta = get_agent_display_meta(name)
            tier_id = meta.get("tier", "tier2")
            
            tier_obj = self._tiers.get(tier_id, self._tiers.get("tier1"))
            default_model = tier_obj.model if tier_obj else (default_tier1 if tier_id in ("tier1", "tier3") else default_tier2)
            default_temp = tier_obj.temperature if tier_obj else 0.70
            default_top_p = tier_obj.top_p if tier_obj else 0.95
            default_tokens = tier_obj.max_output_tokens if tier_obj else 8192

            base_instruction = getattr(agent, "instruction", "") or ""
            if callable(base_instruction):
                try:
                    base_instruction = base_instruction()
                except Exception:
                    base_instruction = str(base_instruction)

            self._canonical_defaults[name] = {
                "tier_id": tier_id,
                "default_model": default_model,
                "default_temperature": default_temp,
                "default_top_p": default_top_p,
                "default_max_output_tokens": default_tokens,
                "system_prompt": str(base_instruction),
            }

        self._apply_overrides_to_live_agents()

    def resolve_effective_config(self, agent_name: str) -> dict[str, Any]:
        """Resolve active and effective runtime parameters for a given agent."""
        canonical = self._canonical_defaults.get(agent_name, {
            "tier_id": "tier2",
            "default_model": self._tiers.get("tier2", self._tiers["tier1"]).model,
            "default_temperature": 0.30,
            "default_top_p": 0.90,
            "default_max_output_tokens": 8192,
            "system_prompt": "",
        })
        override = self._active_overrides.get(agent_name, {})

        assigned_tier_id = (
            override.get("assigned_tier_id")
            or override.get("tier_id")
            or canonical.get("tier_id", "tier1")
        )
        if assigned_tier_id not in self._tiers:
            assigned_tier_id = "tier1"

        tier = self._tiers.get(assigned_tier_id, self._tiers.get("tier1"))

        # Determine config mode
        explicit_mode = override.get("config_mode")
        if explicit_mode in ("inherit", "custom"):
            config_mode = explicit_mode
        else:
            # If explicit model/temp override exists without explicit mode, treat as custom
            has_custom_params = any(
                k in override for k in ("model", "temperature", "top_p", "max_output_tokens")
            )
            config_mode = "custom" if has_custom_params else "inherit"

        if config_mode == "inherit" and tier:
            effective_model = tier.model
            effective_temp = tier.temperature
            effective_top_p = tier.top_p
            effective_tokens = tier.max_output_tokens
            active_model = tier.model
            active_temp = tier.temperature
            active_top_p = tier.top_p
            active_tokens = tier.max_output_tokens
        else:
            # Custom override mode
            effective_model = override.get("model") or (tier.model if tier else canonical["default_model"])
            effective_temp = override.get("temperature", tier.temperature if tier else canonical["default_temperature"])
            effective_top_p = override.get("top_p", tier.top_p if tier else canonical["default_top_p"])
            effective_tokens = override.get("max_output_tokens", tier.max_output_tokens if tier else canonical["default_max_output_tokens"])
            active_model = effective_model
            active_temp = effective_temp
            active_top_p = effective_top_p
            active_tokens = effective_tokens

        custom_prefix = override.get("custom_prompt_prefix", None)
        system_prompt = canonical.get("system_prompt", "")

        is_default = (
            not override
            or (
                config_mode == "inherit"
                and assigned_tier_id == canonical.get("tier_id")
                and not custom_prefix
                and not any(k in override for k in ("model", "temperature", "top_p", "max_output_tokens"))
            )
        )

        return {
            "assigned_tier_id": assigned_tier_id,
            "config_mode": config_mode,
            "model": active_model,
            "default_model": canonical["default_model"],
            "temperature": active_temp,
            "default_temperature": canonical["default_temperature"],
            "top_p": active_top_p,
            "default_top_p": canonical["default_top_p"],
            "max_output_tokens": active_tokens,
            "default_max_output_tokens": canonical["default_max_output_tokens"],
            "custom_prompt_prefix": custom_prefix,
            "system_prompt": system_prompt,
            "is_default": is_default,
            "effective_model": effective_model,
            "effective_temperature": effective_temp,
            "effective_top_p": effective_top_p,
            "effective_max_output_tokens": effective_tokens,
        }

    async def initialize_from_db(self) -> None:
        """Load persisted tiers and agent overrides from MySQL settings table if available."""
        if self._initialized:
            return
        if self.mysql is not None:
            # 1. Load tiers
            try:
                row_tiers = await asyncio.wait_for(
                    self.mysql.fetch_one(
                        "SELECT setting_value FROM settings WHERE setting_key = 'agent_swarm_tiers'"
                    ),
                    timeout=2.0,
                )
                if row_tiers and row_tiers.get("setting_value"):
                    saved_tiers = json.loads(row_tiers["setting_value"])
                    if isinstance(saved_tiers, list):
                        for item in saved_tiers:
                            if isinstance(item, dict) and "id" in item:
                                self._tiers[item["id"]] = ModelTier(**item)
                    elif isinstance(saved_tiers, dict):
                        for k, item in saved_tiers.items():
                            if isinstance(item, dict) and "id" in item:
                                self._tiers[item["id"]] = ModelTier(**item)
            except Exception as exc:
                logger.debug("Failed to load agent tiers from MySQL: %s", exc)

            # 2. Load overrides
            try:
                row_overrides = await asyncio.wait_for(
                    self.mysql.fetch_one(
                        "SELECT setting_value FROM settings WHERE setting_key = 'agent_swarm_overrides'"
                    ),
                    timeout=2.0,
                )
                if row_overrides and row_overrides.get("setting_value"):
                    saved_overrides = json.loads(row_overrides["setting_value"])
                    if isinstance(saved_overrides, dict):
                        for k, v in saved_overrides.items():
                            if isinstance(v, dict):
                                self._active_overrides[k] = v
            except Exception as exc:
                logger.debug("Failed to load agent overrides from MySQL: %s", exc)

            self._apply_overrides_to_live_agents()

        self._initialized = True

    async def initialize_tiers_from_db(self) -> None:
        """Alias helper for initializing tiers from MySQL."""
        await self.initialize_from_db()

    def _apply_overrides_to_live_agents(self) -> None:
        """Apply active in-memory effective parameters directly onto live ADK agent instances."""
        agents = self._get_all_agents()
        for agent in agents:
            name = getattr(agent, "name", "")
            if not hasattr(agent, "model"):
                continue

            resolved = self.resolve_effective_config(name)
            
            # Mutate model on live agent instance
            agent.model = resolved["effective_model"]

            # Mutate instruction with custom prompt prefix if present
            if hasattr(agent, "instruction"):
                prefix = resolved.get("custom_prompt_prefix")
                system_prompt = resolved.get("system_prompt", "")
                if prefix:
                    agent.instruction = f"{prefix.strip()}\n\n{system_prompt}"
                else:
                    agent.instruction = system_prompt

    async def _persist_tiers_to_db(self) -> None:
        """Persist current tier definitions into MySQL settings table."""
        if self.mysql is not None:
            try:
                tiers_payload = [t.model_dump() for t in self._tiers.values()]
                await asyncio.wait_for(
                    self.mysql.execute(
                        """INSERT INTO settings (setting_key, setting_value)
                           VALUES ('agent_swarm_tiers', %s)
                           ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)""",
                        (json.dumps(tiers_payload),),
                    ),
                    timeout=2.0,
                )
            except Exception as exc:
                logger.warning("Failed to persist agent swarm tiers to MySQL: %s", exc)

    async def _persist_overrides_to_db(self) -> None:
        """Persist current agent overrides into MySQL settings table."""
        if self.mysql is not None:
            try:
                await asyncio.wait_for(
                    self.mysql.execute(
                        """INSERT INTO settings (setting_key, setting_value)
                           VALUES ('agent_swarm_overrides', %s)
                           ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)""",
                        (json.dumps(self._active_overrides),),
                    ),
                    timeout=2.0,
                )
            except Exception as exc:
                logger.warning("Failed to persist agent swarm overrides to MySQL: %s", exc)

    # =========================================================================
    # Tier Management CRUD
    # =========================================================================

    async def get_tiers(self) -> list[ModelTier]:
        """Return all registered system and custom model tiers."""
        await self.initialize_from_db()
        return list(self._tiers.values())

    async def get_tier(self, tier_id: str) -> Optional[ModelTier]:
        """Get a specific model tier by identifier."""
        await self.initialize_from_db()
        return self._tiers.get(tier_id)

    async def create_tier(self, payload: TierCreateRequest) -> ModelTier:
        """Create a new custom model tier in registry and persist."""
        await self.initialize_from_db()

        if payload.id:
            tier_id = payload.id.strip().lower()
        else:
            clean_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", payload.name.strip().lower()).strip("_")
            tier_id = f"tier_{clean_slug}"[:64]

        if tier_id in {"tier1", "tier2", "tier3"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create custom tier with reserved system ID '{tier_id}'.",
            )

        if tier_id in self._tiers:
            # Ensure unique id
            tier_id = f"{tier_id[:55]}_{uuid.uuid4().hex[:6]}"

        new_tier = ModelTier(
            id=tier_id,
            name=payload.name,
            description=payload.description or "",
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            max_output_tokens=payload.max_output_tokens,
            color=payload.color,
            is_system=False,
        )
        self._tiers[tier_id] = new_tier
        await self._persist_tiers_to_db()
        return new_tier

    async def update_tier(self, tier_id: str, payload: TierUpdateRequest) -> ModelTier:
        """Update tier parameters and dynamically cascade changes to all inherited member agents."""
        await self.initialize_from_db()
        existing = self._tiers.get(tier_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tier '{tier_id}' not found.",
            )

        updated_dict = existing.model_dump()
        for k, v in payload.model_dump(exclude_none=True).items():
            updated_dict[k] = v
        # Ensure system flag and ID cannot be corrupted
        updated_dict["id"] = existing.id
        updated_dict["is_system"] = existing.is_system

        updated_tier = ModelTier(**updated_dict)
        self._tiers[tier_id] = updated_tier

        # Dynamic cascading to all agents inheriting this tier
        self._apply_overrides_to_live_agents()

        await self._persist_tiers_to_db()
        return updated_tier

    async def delete_tier(self, tier_id: str) -> TierDeleteResponse:
        """Delete custom tier, safely reassign member agents to tier1, and cascade."""
        await self.initialize_from_db()
        existing = self._tiers.get(tier_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tier '{tier_id}' not found.",
            )

        if existing.is_system or tier_id in {"tier1", "tier2", "tier3"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete built-in system tier '{tier_id}'.",
            )

        # Reassign member agents to tier1
        reassigned_count = 0
        all_agents = self._get_all_agents()
        for agent in all_agents:
            agent_name = getattr(agent, "name", "")
            override = self._active_overrides.setdefault(agent_name, {})
            current_tier = (
                override.get("assigned_tier_id")
                or override.get("tier_id")
                or self._canonical_defaults.get(agent_name, {}).get("tier_id", "tier1")
            )
            if current_tier == tier_id:
                override["assigned_tier_id"] = "tier1"
                override["tier_id"] = "tier1"
                reassigned_count += 1

        del self._tiers[tier_id]

        # Apply cascade to live agents
        self._apply_overrides_to_live_agents()

        await self._persist_tiers_to_db()
        await self._persist_overrides_to_db()

        return TierDeleteResponse(
            status="deleted",
            tier_id=tier_id,
            reassigned_agents_count=reassigned_count,
            reassigned_to_tier_id="tier1",
            message=f"Tier '{tier_id}' safely deleted; {reassigned_count} agent(s) reassigned to 'tier1'.",
        )

    # =========================================================================
    # Agent Configuration Endpoints & Inspection
    # =========================================================================

    async def get_agent_configs(self) -> list[AgentConfigItem]:
        """Return structured configuration items for all agents in swarm."""
        await self.initialize_from_db()
        agents = self._get_all_agents()
        configs: list[AgentConfigItem] = []

        for agent in agents:
            name = getattr(agent, "name", "UnnamedAgent")
            meta = get_agent_display_meta(name)
            display_name = meta.get("display_name", name)
            role = meta.get("role", "Specialized Agent")
            
            resolved = self.resolve_effective_config(name)
            
            configs.append(
                AgentConfigItem(
                    agent_id=name,
                    name=name,
                    display_name=display_name,
                    role=role,
                    tier_id=resolved["assigned_tier_id"],
                    assigned_tier_id=resolved["assigned_tier_id"],
                    config_mode=resolved["config_mode"],
                    model=resolved["model"],
                    temperature=resolved["temperature"],
                    top_p=resolved["top_p"],
                    max_output_tokens=resolved["max_output_tokens"],
                    custom_prompt_prefix=resolved["custom_prompt_prefix"],
                    system_prompt=resolved["system_prompt"],
                    effective_model=resolved["effective_model"],
                    effective_temperature=resolved["effective_temperature"],
                    effective_top_p=resolved["effective_top_p"],
                    effective_max_output_tokens=resolved["effective_max_output_tokens"],
                    is_default=resolved["is_default"],
                )
            )

        return configs

    async def update_agent_configs(
        self, overrides: list[AgentConfigOverrideItem]
    ) -> AgentConfigBatchUpdateResponse:
        """Batch update agent tier assignments, configuration modes, and parameters."""
        await self.initialize_from_db()
        all_agent_names = {getattr(a, "name", "") for a in self._get_all_agents()}
        
        updated: list[str] = []
        for item in overrides:
            if item.agent_id not in all_agent_names:
                continue

            current_override = self._active_overrides.get(item.agent_id, {})
            dumped = item.model_dump(exclude_none=True)
            dumped.pop("agent_id", None)
            
            if "assigned_tier_id" in dumped:
                dumped["tier_id"] = dumped["assigned_tier_id"]
            elif "tier_id" in dumped:
                dumped["assigned_tier_id"] = dumped["tier_id"]

            current_override.update(dumped)
            self._active_overrides[item.agent_id] = current_override
            updated.append(item.agent_id)

        # Apply to live agent instances
        self._apply_overrides_to_live_agents()
        await self._persist_overrides_to_db()

        updated_configs = await self.get_agent_configs()

        return AgentConfigBatchUpdateResponse(
            success=True,
            message=f"Successfully updated configuration for {len(updated)} agent(s).",
            updated_agents=updated,
            agents=updated_configs,
        )

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
            meta_info = get_agent_display_meta(name)
            display_name = meta_info.get("display_name", name)
            role = meta_info.get("role", "Specialized Agent")
            
            # Sub agents
            sub_agent_names: list[str] = []
            for sub in getattr(agent, "sub_agents", []) or []:
                sub_name = getattr(sub, "name", None)
                if sub_name == "WriterReviewerLoop":
                    for loop_sub in getattr(sub, "sub_agents", []) or []:
                        ls_name = getattr(loop_sub, "name", None)
                        if ls_name:
                            sub_agent_names.append(ls_name)
                elif sub_name:
                    sub_agent_names.append(sub_name)

            # Tools
            tool_definitions: list[AgentToolDefinition] = []
            for tool in getattr(agent, "tools", []) or []:
                tool_definitions.append(extract_tool_schema(tool))

            resolved = self.resolve_effective_config(name)

            config = AgentConfig(
                config_mode=resolved["config_mode"],
                assigned_tier_id=resolved["assigned_tier_id"],
                model=resolved["model"],
                default_model=resolved["default_model"],
                temperature=resolved["temperature"],
                default_temperature=resolved["default_temperature"],
                top_p=resolved["top_p"],
                default_top_p=resolved["default_top_p"],
                max_output_tokens=resolved["max_output_tokens"],
                default_max_output_tokens=resolved["default_max_output_tokens"],
                custom_prompt_prefix=resolved["custom_prompt_prefix"],
                system_prompt=resolved["system_prompt"],
                is_default=resolved["is_default"],
                effective_model=resolved["effective_model"],
                effective_temperature=resolved["effective_temperature"],
                effective_top_p=resolved["effective_top_p"],
                effective_max_output_tokens=resolved["effective_max_output_tokens"],
            )

            agent_metas.append(
                AgentMetadata(
                    name=name,
                    display_name=display_name,
                    description=description,
                    role=role,
                    tier=resolved["assigned_tier_id"],
                    assigned_tier_id=resolved["assigned_tier_id"],
                    config_mode=resolved["config_mode"],
                    sub_agents=sub_agent_names,
                    tools=tool_definitions,
                    config=config,
                )
            )

        return AgentRegistryResponse(
            agents=agent_metas,
            total=len(agent_metas),
            tiers=list(self._tiers.values()),
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
            if "assigned_tier_id" in dumped:
                dumped["tier_id"] = dumped["assigned_tier_id"]
            elif "tier_id" in dumped:
                dumped["assigned_tier_id"] = dumped["tier_id"]

            current_override.update(dumped)
            self._active_overrides[agent_name] = current_override
            updated.append(agent_name)

        # Apply immediately to live agent instances
        self._apply_overrides_to_live_agents()
        await self._persist_overrides_to_db()

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
            self._init_default_tiers()
            reset_agents.extend(all_agent_names)

        # Apply reset to live instances
        self._apply_overrides_to_live_agents()
        await self._persist_tiers_to_db()
        await self._persist_overrides_to_db()

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
