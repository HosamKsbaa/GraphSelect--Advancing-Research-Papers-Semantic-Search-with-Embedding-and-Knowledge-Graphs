"""Project lifecycle tools for the Orchestrator Agent.

Each function is an async ADK tool that wraps the projects service layer.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


async def create_new_project(
    name: str,
    topic: str,
    description: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Create and activate a new research project.

    Use this tool when the user wants to start a new literature review,
    create a new project, or investigate a new topic. Sets the newly
    created project as the active project in the session.

    Args:
        name: A short, descriptive name for the project (e.g., "Bread Making Techniques").
        topic: The main topic or research domain (e.g., "fermentation and baking methods").
        description: Optional detailed description of what you want to research.
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with the created project details.
    """
    try:
        from projects.models import ProjectCreate
        from projects.service import create_project

        # Access services from registry
        neo4j = ServiceRegistry.neo4j
        log_service = ServiceRegistry.log_service
        mysql = log_service._mysql

        data = ProjectCreate(
            name=name,
            topic=topic,
            description=description or f"Literature review on {topic}",
        )

        project = await create_project(data, mysql, neo4j)

        # Set the active project in tool context state
        if tool_context is not None and hasattr(tool_context, "state") and tool_context.state is not None:
            tool_context.state["project_id"] = project.id

        return {
            "status": "created",
            "project_id": project.id,
            "name": project.name,
            "topic": project.topic,
            "description": project.description,
            "message": f"Successfully created and activated project '{project.name}' with ID '{project.id}'.",
        }
    except Exception as exc:
        logger.error("create_new_project failed: %s", exc)
        return {"error": str(exc)}


async def select_project(
    project_id: str,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Select and activate an existing project.

    Use this tool when the user specifies an existing project ID or name
    they want to work on. Sets the selected project as the active project.

    Args:
        project_id: The UUID of the project to activate.
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict with the selected project details.
    """
    try:
        from projects.service import get_project

        log_service = ServiceRegistry.log_service
        mysql = log_service._mysql

        project = await get_project(project_id, mysql)
        if project is None:
            return {"error": f"Project with ID '{project_id}' not found."}

        # Set the active project in tool context state
        if tool_context is not None and hasattr(tool_context, "state") and tool_context.state is not None:
            tool_context.state["project_id"] = project.id

        return {
            "status": "activated",
            "project_id": project.id,
            "name": project.name,
            "topic": project.topic,
            "message": f"Successfully activated project '{project.name}' with ID '{project.id}'.",
        }
    except Exception as exc:
        logger.error("select_project failed: %s", exc)
        return {"error": str(exc)}


async def list_projects(
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """List all available research projects.

    Use this tool when the user wants to see their existing projects.

    Args:
        tool_context: ADK tool context (auto-injected).

    Returns:
        A dict containing a list of all projects.
    """
    try:
        from projects.service import get_projects

        log_service = ServiceRegistry.log_service
        mysql = log_service._mysql

        projects_list = await get_projects(mysql, include_archived=False)
        return {
            "projects": [
                {
                    "project_id": p.id,
                    "name": p.name,
                    "topic": p.topic,
                    "status": p.status,
                }
                for p in projects_list
            ],
            "total": len(projects_list),
        }
    except Exception as exc:
        logger.error("list_projects failed: %s", exc)
        return {"error": str(exc), "projects": [], "total": 0}
