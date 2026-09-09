"""FastAPI router for Agent Swarm Inspector, Tier Management & Configuration endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from agents.agent import root_agent
from features.agents.models import (
    AgentConfigBatchUpdateRequest,
    AgentConfigBatchUpdateResponse,
    AgentConfigListResponse,
    AgentConfigUpdate,
    AgentRegistryResponse,
    AgentResetRequest,
    AgentResetResponse,
    AgentSettingsUpdateRequest,
    AgentSettingsUpdateResponse,
    AgentTraceListResponse,
    ModelTier,
    TierCreateRequest,
    TierDeleteResponse,
    TierListResponse,
    TierUpdateRequest,
)
from features.agents.service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Singleton service instance cache
_agent_service: Optional[AgentService] = None


def get_agent_service(request: Request) -> AgentService:
    """Dependency / helper to retrieve or construct the AgentService singleton."""
    global _agent_service
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if _agent_service is None:
        _agent_service = AgentService(root_agent=root_agent, neo4j_service=neo4j_service)
    else:
        if getattr(_agent_service, "neo4j", None) is None and neo4j_service is not None:
            _agent_service.neo4j = neo4j_service
    return _agent_service


# ============================================================================
# Tier Management Endpoints (Milestone 1)
# ============================================================================

@router.get("/tiers", response_model=TierListResponse)
async def get_tiers(request: Request) -> TierListResponse:
    """List all system and custom model tiers with default sampling parameters."""
    service = get_agent_service(request)
    tiers = await service.get_tiers()
    return TierListResponse(tiers=tiers, total=len(tiers))


@router.post("/tiers", response_model=ModelTier, status_code=status.HTTP_201_CREATED)
async def create_tier(payload: TierCreateRequest, request: Request) -> ModelTier:
    """Create a new custom model tier."""
    service = get_agent_service(request)
    return await service.create_tier(payload)


@router.put("/tiers/{tier_id}", response_model=ModelTier)
async def update_tier(tier_id: str, payload: TierUpdateRequest, request: Request) -> ModelTier:
    """Update a model tier and dynamically cascade updated defaults to all inherited agents."""
    service = get_agent_service(request)
    tier = await service.get_tier(tier_id)
    if tier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tier '{tier_id}' not found.",
        )
    return await service.update_tier(tier_id, payload)


@router.delete("/tiers/{tier_id}", response_model=TierDeleteResponse)
async def delete_tier(tier_id: str, request: Request) -> TierDeleteResponse:
    """Delete a custom tier and safely reassign all assigned member agents to tier1."""
    service = get_agent_service(request)
    tier = await service.get_tier(tier_id)
    if tier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tier '{tier_id}' not found.",
        )
    if tier.is_system or tier_id in {"tier1", "tier2", "tier3"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete built-in system tier '{tier_id}'.",
        )

    return await service.delete_tier(tier_id)


# ============================================================================
# Agent Configuration Endpoints
# ============================================================================

@router.get("/config", response_model=AgentConfigListResponse)
async def get_agent_config(request: Request) -> AgentConfigListResponse:
    """Retrieve full configuration state, mode, tier assignment, and effective parameters for all agents."""
    service = get_agent_service(request)
    configs = await service.get_agent_configs()
    return AgentConfigListResponse(agents=configs, total=len(configs))


@router.put("/config", response_model=AgentConfigBatchUpdateResponse)
async def update_agent_config(
    payload: AgentConfigBatchUpdateRequest, request: Request
) -> AgentConfigBatchUpdateResponse:
    """Batch update agent tier assignments, configuration modes ('inherit' | 'custom'), and custom overrides."""
    service = get_agent_service(request)
    registry = await service.get_registry()
    valid_agent_names = {a.name for a in registry.agents}

    # Validate agent names
    unknown_agents = [item.agent_id for item in payload.overrides if item.agent_id not in valid_agent_names]
    if unknown_agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent(s): {', '.join(unknown_agents)}.",
        )

    # Validate tier_ids
    existing_tiers = {t.id for t in await service.get_tiers()}
    unknown_tiers = [
        item.tier_id for item in payload.overrides
        if item.tier_id is not None and item.tier_id not in existing_tiers
    ]
    if unknown_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tier_id(s): {', '.join(unknown_tiers)}. Available tiers: {', '.join(sorted(existing_tiers))}",
        )

    return await service.update_agent_configs(payload.overrides)


# ============================================================================
# Core Registry & Settings Endpoints
# ============================================================================

@router.get("/registry", response_model=AgentRegistryResponse)
async def get_agent_registry(request: Request) -> AgentRegistryResponse:
    """Introspect the live ADK agent tree and return all agents, tools, schemas, and configurations."""
    service = get_agent_service(request)
    return await service.get_registry()


@router.put("/settings", response_model=AgentSettingsUpdateResponse)
async def update_agent_settings(
    payload: AgentSettingsUpdateRequest,
    request: Request,
) -> AgentSettingsUpdateResponse:
    """Update and hot-reload runtime configuration parameters for specified agents."""
    service = get_agent_service(request)
    
    # Validate agent names exist
    registry = await service.get_registry()
    valid_names = {a.name for a in registry.agents}
    
    unknown = [name for name in payload.settings.keys() if name not in valid_names]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent(s): {', '.join(unknown)}. Valid agents: {', '.join(sorted(valid_names))}",
        )

    return await service.update_settings(payload.settings)


@router.post("/settings/reset", response_model=AgentResetResponse)
async def reset_agent_settings(
    payload: AgentResetRequest,
    request: Request,
) -> AgentResetResponse:
    """Reset individual or all agents back to canonical factory defaults."""
    service = get_agent_service(request)
    if payload.agent_name:
        registry = await service.get_registry()
        valid_names = {a.name for a in registry.agents}
        if payload.agent_name not in valid_names:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent '{payload.agent_name}' not found.",
            )

    return await service.reset_settings(agent_name=payload.agent_name)


@router.get("/traces", response_model=AgentTraceListResponse)
async def get_agent_traces(
    request: Request,
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    since: Optional[datetime] = Query(None, description="Filter traces created after timestamp"),
    limit: int = Query(100, ge=1, le=500, description="Max traces to return"),
) -> AgentTraceListResponse:
    """Query recent LLM execution traces filterable by agent name and project."""
    service = get_agent_service(request)
    traces = await service.get_traces(
        agent_name=agent_name,
        project_id=project_id,
        since=since,
        limit=limit,
    )
    return AgentTraceListResponse(traces=traces, total=len(traces))
