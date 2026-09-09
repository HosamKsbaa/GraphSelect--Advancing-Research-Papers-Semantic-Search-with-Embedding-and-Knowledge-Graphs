"""Session management API endpoints for ALRS v2 backed by pure Neo4j epistemic graph."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.db.neo4j_service import Neo4jService
from core.dependencies import get_neo4j_service
from features.sessions.models import SearchMode, SessionList, SessionRead, SessionStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _parse_session_node(data: dict[str, Any]) -> SessionRead:
    """Map Neo4j node attributes to SessionRead model under 25 lines."""
    raw_q = data.get("research_questions", [])
    if isinstance(raw_q, str):
        try:
            questions = json.loads(raw_q)
        except Exception:
            questions = [raw_q] if raw_q else []
    else:
        questions = list(raw_q) if raw_q else []

    created = data.get("created_at") or datetime.now(timezone.utc)
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))

    updated = data.get("updated_at")
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))

    mode_val = str(data.get("mode", "interactive")).lower()
    mode = SearchMode.AUTOMATED if mode_val == "automated" else SearchMode.INTERACTIVE

    status_val = str(data.get("status", "created")).lower()
    stat_enum = getattr(SessionStatus, status_val.upper(), SessionStatus.CREATED)

    return SessionRead(
        session_id=str(data.get("campaign_id") or data.get("session_id", "")),
        seed_doi=str(data.get("seed_doi", "")),
        research_questions=questions,
        similarity_threshold=float(data.get("similarity_threshold", 0.5)),
        max_depth=int(data.get("max_depth", 2)),
        mode=mode,
        status=stat_enum,
        papers_discovered=int(data.get("papers_discovered", 0)),
        papers_relevant=int(data.get("papers_relevant", 0)),
        current_depth=int(data.get("current_depth", 0)),
        created_at=created,
        updated_at=updated,
    )


@router.get("", response_model=SessionList)
async def list_sessions(
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> SessionList:
    """Return every active research campaign session stored in Neo4j."""
    query = (
        "MATCH (c:ResearchCampaign) "
        "RETURN c "
        "ORDER BY c.created_at DESC"
    )
    records = await neo4j.execute_read(query)
    sessions: list[SessionRead] = []
    for r in records:
        node = r.get("c", {})
        if hasattr(node, "items"):
            props = dict(node)
        elif isinstance(node, dict):
            props = node
        else:
            props = {}
        sessions.append(_parse_session_node(props))
    return SessionList(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: str,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> SessionRead:
    """Fetch a single campaign session by its UUID from Neo4j."""
    query = (
        "MATCH (c:ResearchCampaign) "
        "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
        "RETURN c LIMIT 1"
    )
    records = await neo4j.execute_read(query, {"session_id": session_id})
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    node = records[0].get("c", {})
    props = dict(node) if hasattr(node, "items") else dict(node)
    return _parse_session_node(props)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, str]:
    """Delete a research campaign session and cascade associated substates."""
    query = (
        "MATCH (c:ResearchCampaign) "
        "WHERE c.campaign_id = $session_id OR c.session_id = $session_id "
        "DETACH DELETE c "
        "RETURN count(c) AS deleted_count"
    )
    records = await neo4j.execute_write(query, {"session_id": session_id})
    deleted = records[0].get("deleted_count", 0) if records else 0
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return {"message": f"Session {session_id} deleted"}
