"""Session management API endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from models.session import SessionRead, SessionList, SessionStatus, SearchMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionList)
async def list_sessions() -> SessionList:
    """List all search sessions."""
    from main import mysql_service

    if mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL service not initialized",
        )

    rows = await mysql_service.fetch_all(
        "SELECT * FROM sessions ORDER BY created_at DESC"
    )
    sessions: list[SessionRead] = []
    for row in rows:
        questions_raw = row.get("research_questions", "[]")
        questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw
        sessions.append(
            SessionRead(
                session_id=str(row["session_id"]),
                seed_doi=str(row["seed_doi"]),
                research_questions=questions,
                similarity_threshold=float(row["similarity_threshold"]),
                max_depth=int(row["max_depth"]),
                mode=SearchMode(str(row["mode"])),
                status=SessionStatus(str(row["status"])),
                papers_discovered=int(row.get("papers_discovered", 0)),
                papers_relevant=int(row.get("papers_relevant", 0)),
                current_depth=int(row.get("current_depth", 0)),
                created_at=row["created_at"],
                updated_at=row.get("updated_at"),
            )
        )
    return SessionList(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str) -> SessionRead:
    """Get a specific session by ID."""
    from main import mysql_service

    if mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL service not initialized",
        )

    row = await mysql_service.fetch_one(
        "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    questions_raw = row.get("research_questions", "[]")
    questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw

    return SessionRead(
        session_id=str(row["session_id"]),
        seed_doi=str(row["seed_doi"]),
        research_questions=questions,
        similarity_threshold=float(row["similarity_threshold"]),
        max_depth=int(row["max_depth"]),
        mode=SearchMode(str(row["mode"])),
        status=SessionStatus(str(row["status"])),
        papers_discovered=int(row.get("papers_discovered", 0)),
        papers_relevant=int(row.get("papers_relevant", 0)),
        current_depth=int(row.get("current_depth", 0)),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a session and its associated data."""
    from main import mysql_service

    if mysql_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL service not initialized",
        )

    deleted = await mysql_service.execute(
        "DELETE FROM sessions WHERE session_id = %s", (session_id,)
    )
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return {"message": f"Session {session_id} deleted"}
