"""FastAPI router for Agent Swarm Inspector & Configuration endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from agents.agent import root_agent
from features.agents.models import (
    AgentConfigUpdate,
    AgentRegistryResponse,
    AgentResetRequest,
    AgentResetResponse,
    AgentSettingsUpdateRequest,
    AgentSettingsUpdateResponse,
    AgentTraceListResponse,
)
from features.agents.service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Singleton service instance cache
_agent_service: Optional[AgentService] = None


def get_agent_service(request: Request) -> AgentService:
    """Dependency / helper to retrieve or construct the AgentService singleton."""
    global _agent_service
    mysql_service = getattr(request.app.state, "mysql_service", None)
    if _agent_service is None:
        _agent_service = AgentService(root_agent=root_agent, mysql_service=mysql_service)
    else:
        # Update mysql reference if it became available after startup
        if _agent_service.mysql is None and mysql_service is not None:
            _agent_service.mysql = mysql_service
    return _agent_service


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
