"""Project lifecycle service for ALRS v2 (Pure Neo4j Persistence).

Manages project CRUD exclusively via Neo4j graph nodes (:Project and :ResearchCampaign).
Complies with Constitution C8 (Zero MySQL) and Sub-25 line functions (C1, C9).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.db.neo4j_service import Neo4jService
from projects.models import ProjectCreate, ProjectResponse, ProjectUpdate

logger = logging.getLogger(__name__)


def _parse_dt(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None
    return None


def _record_to_response(rec: dict[str, Any]) -> ProjectResponse:
    """Map a Neo4j record dict to a ProjectResponse model."""
    c_at = rec.get("created_at")
    u_at = rec.get("updated_at")
    l_at = rec.get("last_accessed_at")
    return ProjectResponse(
        id=str(rec.get("project_id", "")),
        name=str(rec.get("name", "")),
        description=rec.get("description"),
        topic=rec.get("topic"),
        target_level=str(rec.get("target_level", "master")),
        similarity_threshold=float(rec.get("similarity_threshold", 0.6)),
        token_budget=int(rec.get("token_budget", 500000)),
        status=str(rec.get("status", "active")),
        created_at=_parse_dt(c_at),
        updated_at=_parse_dt(u_at),
        last_accessed_at=_parse_dt(l_at),
        paper_count=int(rec.get("paper_count", 0)),
        question_count=int(rec.get("question_count", 0)),
    )


async def create_project(
    data: ProjectCreate,
    neo4j: Neo4jService,
) -> ProjectResponse:
    """Create a new project node in Neo4j."""
    project_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    query = """
    MERGE (pr:Project {project_id: $id})
    ON CREATE SET pr.created_at = datetime()
    SET pr.name = $name,
        pr.description = $description,
        pr.topic = $topic,
        pr.target_level = $target_level,
        pr.similarity_threshold = $similarity_threshold,
        pr.token_budget = $token_budget,
        pr.status = 'active',
        pr.updated_at = datetime(),
        pr.last_accessed_at = datetime()
    RETURN pr.project_id AS project_id, pr.name AS name,
           pr.description AS description, pr.topic AS topic,
           pr.target_level AS target_level, pr.similarity_threshold AS similarity_threshold,
           pr.token_budget AS token_budget, pr.status AS status
    """
    params = {
        "id": project_id,
        "name": data.name,
        "description": data.description,
        "topic": data.topic,
        "target_level": data.target_level,
        "similarity_threshold": data.similarity_threshold,
        "token_budget": data.token_budget,
    }
    await neo4j.execute_write(query, params)
    logger.info("Project created in Neo4j: %s (%s)", project_id, data.name)
    return ProjectResponse(
        id=project_id,
        name=data.name,
        description=data.description,
        topic=data.topic,
        target_level=data.target_level,
        similarity_threshold=data.similarity_threshold,
        token_budget=data.token_budget,
        status="active",
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
    )


async def get_project(
    project_id: str,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Fetch a single project by ID from Neo4j."""
    query = """
    MATCH (pr:Project {project_id: $project_id})
    OPTIONAL MATCH (pr)-[:HAS_PAPER]->(p:Paper)
    OPTIONAL MATCH (q:ResearchQuestion {project_id: pr.project_id})
    RETURN pr.project_id AS project_id, pr.name AS name,
           pr.description AS description, pr.topic AS topic,
           pr.target_level AS target_level, pr.similarity_threshold AS similarity_threshold,
           pr.token_budget AS token_budget, pr.status AS status,
           count(DISTINCT p) AS paper_count, count(DISTINCT q) AS question_count
    """
    records = await neo4j.execute_read(query, {"project_id": project_id})
    if not records or not records[0].get("project_id"):
        return None
    return _record_to_response(records[0])


async def get_projects(
    neo4j: Neo4jService,
    include_archived: bool = False,
) -> list[ProjectResponse]:
    """List all projects from Neo4j, optionally including archived ones."""
    filter_clause = "" if include_archived else "WHERE pr.status <> 'archived'"
    query = f"""
    MATCH (pr:Project)
    {filter_clause}
    OPTIONAL MATCH (pr)-[:HAS_PAPER]->(p:Paper)
    OPTIONAL MATCH (q:ResearchQuestion {{project_id: pr.project_id}})
    RETURN pr.project_id AS project_id, pr.name AS name,
           pr.description AS description, pr.topic AS topic,
           pr.target_level AS target_level, pr.similarity_threshold AS similarity_threshold,
           pr.token_budget AS token_budget, pr.status AS status,
           count(DISTINCT p) AS paper_count, count(DISTINCT q) AS question_count
    ORDER BY pr.project_id DESC
    """
    records = await neo4j.execute_read(query)
    return [_record_to_response(r) for r in records if r.get("project_id")]


async def update_project(
    project_id: str,
    data: ProjectUpdate,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Update a project's fields in Neo4j."""
    update_dict = data.model_dump(exclude_unset=True)
    if not update_dict:
        return await get_project(project_id, neo4j)
    set_clauses = ["pr.updated_at = datetime()"]
    for k in update_dict:
        set_clauses.append(f"pr.{k} = ${k}")
    query = f"""
    MATCH (pr:Project {project_id: $project_id})
    SET {', '.join(set_clauses)}
    RETURN pr.project_id AS project_id
    """
    params = dict(update_dict)
    params["project_id"] = project_id
    records = await neo4j.execute_write(query, params)
    if not records:
        return None
    return await get_project(project_id, neo4j)


async def archive_project(
    project_id: str,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Soft-delete a project by setting status to 'archived'."""
    query = """
    MATCH (pr:Project {project_id: $project_id})
    SET pr.status = 'archived', pr.updated_at = datetime()
    RETURN pr.project_id AS project_id
    """
    records = await neo4j.execute_write(query, {"project_id": project_id})
    if not records:
        return None
    return await get_project(project_id, neo4j)


async def touch_project(
    project_id: str,
    neo4j: Neo4jService,
) -> ProjectResponse | None:
    """Update last_accessed_at timestamp in Neo4j."""
    query = """
    MATCH (pr:Project {project_id: $project_id})
    SET pr.last_accessed_at = datetime()
    RETURN pr.project_id AS project_id
    """
    records = await neo4j.execute_write(query, {"project_id": project_id})
    if not records:
        return None
    return await get_project(project_id, neo4j)
