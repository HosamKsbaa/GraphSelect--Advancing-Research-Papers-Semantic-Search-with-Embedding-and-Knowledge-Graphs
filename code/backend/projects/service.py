"""Project lifecycle service for ALRS v2.

Manages project CRUD across both MySQL (relational metadata) and Neo4j
(graph node). All mutations are dual-write: MySQL holds the authoritative
record, Neo4j holds the graph representation for relationship queries.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from projects.models import ProjectCreate, ProjectResponse, ProjectUpdate

if TYPE_CHECKING:
    from core.db.mysql_service import MySQLService
    from core.db.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)


async def create_project(
    data: ProjectCreate,
    mysql: MySQLService,
    neo4j: Neo4jService,
) -> ProjectResponse:
    """Create a new project in both MySQL and Neo4j.

    Generates a UUID, inserts into MySQL (authoritative), then creates
    a matching Project node in Neo4j for graph queries.

    Args:
        data: Validated project creation payload.
        mysql: MySQL service instance.
        neo4j: Neo4j service instance.

    Returns:
        The created project as a ProjectResponse.
    """
    project_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)

    # MySQL insert (authoritative store)
    await mysql.execute(
        '''INSERT INTO projects (id, name, description, topic, target_level,
           similarity_threshold, token_budget, status, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (
            project_id,
            data.name,
            data.description,
            data.topic,
            data.target_level,
            data.similarity_threshold,
            data.token_budget,
            'active',
            now,
            now,
        ),
    )

    # Neo4j node (graph representation)
    await neo4j.create_project_node(
        project_id=project_id,
        name=data.name,
        status='active',
    )

    logger.info('Project created: %s (%s)', project_id, data.name)
    return ProjectResponse(
        id=project_id,
        name=data.name,
        description=data.description,
        topic=data.topic,
        target_level=data.target_level,
        similarity_threshold=data.similarity_threshold,
        token_budget=data.token_budget,
        status='active',
        created_at=now,
        updated_at=now,
    )


async def get_project(
    project_id: str,
    mysql: MySQLService,
) -> ProjectResponse | None:
    """Fetch a single project by ID from MySQL.

    Args:
        project_id: UUID of the project.
        mysql: MySQL service instance.

    Returns:
        ProjectResponse or None if not found.
    """
    row = await mysql.fetch_one(
        'SELECT * FROM projects WHERE id = %s',
        (project_id,),
    )
    if row is None:
        return None
    return _row_to_response(row)


async def get_projects(
    mysql: MySQLService,
    include_archived: bool = False,
) -> list[ProjectResponse]:
    """List all projects, optionally including archived ones.

    Args:
        mysql: MySQL service instance.
        include_archived: If True, include archived projects.

    Returns:
        List of ProjectResponse instances.
    """
    if include_archived:
        rows = await mysql.fetch_all(
            'SELECT * FROM projects ORDER BY created_at DESC',
        )
    else:
        rows = await mysql.fetch_all(
            "SELECT * FROM projects WHERE status != 'archived' ORDER BY created_at DESC",
        )
    return [_row_to_response(row) for row in rows]


async def update_project(
    project_id: str,
    data: ProjectUpdate,
    mysql: MySQLService,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Update a project's fields in MySQL and sync name to Neo4j.

    Args:
        project_id: UUID of the project.
        data: Validated update payload (only set fields are applied).
        mysql: MySQL service instance.
        neo4j: Neo4j service instance.

    Returns:
        Updated ProjectResponse or None if project not found.
    """
    # Build dynamic SET clause from non-None fields
    updates: list[str] = []
    params: list[object] = []

    update_dict = data.model_dump(exclude_unset=True)
    if not update_dict:
        # Nothing to update, just return current state
        return await get_project(project_id, mysql)

    for field, value in update_dict.items():
        updates.append(f'{field} = %s')
        params.append(value)

    params.append(project_id)
    sql = f"UPDATE projects SET {', '.join(updates)} WHERE id = %s"
    affected = await mysql.execute(sql, tuple(params))

    if affected == 0:
        return None

    # Sync name to Neo4j if it was updated
    if 'name' in update_dict:
        try:
            await neo4j.execute_write(
                """MATCH (pr:Project {project_id: $project_id})
                   SET pr.name = $name, pr.updated_at = datetime()""",
                {'project_id': project_id, 'name': update_dict['name']},
            )
        except Exception as e:
            logger.warning('Failed to sync project name to Neo4j: %s', e)

    return await get_project(project_id, mysql)


async def archive_project(
    project_id: str,
    mysql: MySQLService,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Soft-delete a project by setting status to 'archived'.

    Updates both MySQL (authoritative) and Neo4j (graph).

    Args:
        project_id: UUID of the project.
        mysql: MySQL service instance.
        neo4j: Neo4j service instance.

    Returns:
        Updated ProjectResponse or None if project not found.
    """
    affected = await mysql.execute(
        "UPDATE projects SET status = 'archived' WHERE id = %s",
        (project_id,),
    )
    if affected == 0:
        return None

    try:
        await neo4j.archive_project(project_id)
    except Exception as e:
        logger.warning('Failed to archive project in Neo4j: %s', e)

    logger.info('Project archived: %s', project_id)
    return await get_project(project_id, mysql)


def _row_to_response(row: dict[str, Any]) -> ProjectResponse:
    """Map a MySQL row dict to a ProjectResponse model.

    Args:
        row: Dict from MySQL fetch with column names as keys.

    Returns:
        ProjectResponse instance.
    """
    return ProjectResponse(
        id=str(row['id']),
        name=str(row['name']),
        description=row.get('description'),  # type: ignore[arg-type]
        topic=row.get('topic'),  # type: ignore[arg-type]
        target_level=str(row.get('target_level', 'master')),
        similarity_threshold=float(row.get('similarity_threshold', 0.6)),
        token_budget=int(row.get('token_budget', 500000)),
        status=str(row.get('status', 'active')),
        created_at=row.get('created_at'),  # type: ignore[arg-type]
        updated_at=row.get('updated_at'),  # type: ignore[arg-type]
    )
