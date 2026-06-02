"""Project management REST router for ALRS v2.

Exposes CRUD endpoints for research projects under ``/api/projects``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.db.mysql_service import MySQLService
from core.db.neo4j_service import Neo4jService
from core.dependencies import get_mysql_service, get_neo4j_service
from projects.models import ProjectCreate, ProjectResponse, ProjectUpdate
from projects import service as project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new research project",
)
async def create_project(
    data: ProjectCreate,
    mysql: MySQLService = Depends(get_mysql_service),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> ProjectResponse:
    """Create a new research project with the given parameters."""
    return await project_service.create_project(data, mysql, neo4j)


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List all projects",
)
async def list_projects(
    include_archived: bool = Query(default=False, description="Include archived projects"),
    mysql: MySQLService = Depends(get_mysql_service),
) -> list[ProjectResponse]:
    """List all research projects, optionally including archived ones."""
    return await project_service.get_projects(mysql, include_archived=include_archived)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project by ID",
)
async def get_project(
    project_id: str,
    mysql: MySQLService = Depends(get_mysql_service),
) -> ProjectResponse:
    """Fetch a single project by its UUID."""
    result = await project_service.get_project(project_id, mysql)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return result


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    mysql: MySQLService = Depends(get_mysql_service),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> ProjectResponse:
    """Update fields of an existing project."""
    result = await project_service.update_project(project_id, data, mysql, neo4j)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return result


@router.patch(
    "/{project_id}/archive",
    response_model=ProjectResponse,
    summary="Archive a project",
)
async def archive_project(
    project_id: str,
    mysql: MySQLService = Depends(get_mysql_service),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> ProjectResponse:
    """Soft-delete a project by setting its status to 'archived'."""
    result = await project_service.archive_project(project_id, mysql, neo4j)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return result
