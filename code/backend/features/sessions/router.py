"""Session management API endpoints for ALRS v2.

This router provides CRUD operations for literature-review search
sessions.  It is deliberately *thin* — all data comes from the MySQL
``sessions`` table via :class:`~core.db.mysql_service.MySQLService`, and no
business logic beyond simple row-to-model mapping happens here.

Implementation note — manual ``SessionRead`` construction:
    MySQL returns ``research_questions`` as a JSON-encoded string
    (``TEXT`` column), so every endpoint must deserialise it with
    :func:`json.loads` before handing it to the Pydantic model.
    The remaining columns are also explicitly cast to their Python
    types to guard against driver-level type ambiguities (e.g.
    ``Decimal`` vs ``float`` for thresholds).

Endpoints:
    GET    /api/sessions              → list all sessions, newest first
    GET    /api/sessions/{session_id} → single session by UUID
    DELETE /api/sessions/{session_id} → remove session and cascade data
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends

from features.sessions.models import SessionRead, SessionList, SessionStatus, SearchMode
from core.db.mysql_service import MySQLService
from core.dependencies import get_mysql_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("", response_model=SessionList)
async def list_sessions(
    mysql: MySQLService = Depends(get_mysql_service),
) -> SessionList:
    """Return every search session stored in MySQL, newest first.

    Each row's ``research_questions`` column is a JSON-encoded string
    that must be parsed before it can populate the Pydantic list field.

    Args:
        mysql: Injected MySQL service (via FastAPI DI).

    Returns:
        A ``SessionList`` envelope containing all sessions and their
        total count.
    """
    rows = await mysql.fetch_all(
        "SELECT * FROM sessions ORDER BY created_at DESC"
    )
    sessions: list[SessionRead] = []
    for row in rows:
        # research_questions is stored as a JSON TEXT column in MySQL;
        # parse it into a Python list so Pydantic can validate it.
        questions_raw = row.get("research_questions", "[]")
        questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw

        # Construct the response model manually, casting each column to
        # its expected Python type to handle driver-level ambiguities
        # (e.g. Decimal → float, bytes → str).
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
async def get_session(
    session_id: str,
    mysql: MySQLService = Depends(get_mysql_service),
) -> SessionRead:
    """Fetch a single search session by its UUID.

    Args:
        session_id: The UUID of the session to retrieve.
        mysql: Injected MySQL service (via FastAPI DI).

    Returns:
        The fully populated ``SessionRead`` model for this session.

    Raises:
        HTTPException 404: If no row exists for the given *session_id*.
    """
    row = await mysql.fetch_one(
        "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Deserialise the JSON-encoded research_questions column.
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
async def delete_session(
    session_id: str,
    mysql: MySQLService = Depends(get_mysql_service),
) -> dict[str, str]:
    """Delete a session and its associated data by UUID.

    Uses the row-count returned by ``MySQLService.execute()`` to detect
    whether the session actually existed before attempting deletion.

    Args:
        session_id: The UUID of the session to delete.
        mysql: Injected MySQL service (via FastAPI DI).

    Returns:
        A confirmation dict ``{"message": "Session <id> deleted"}``.

    Raises:
        HTTPException 404: If no row was affected (session not found).
    """
    deleted = await mysql.execute(
        "DELETE FROM sessions WHERE session_id = %s", (session_id,)
    )
    # execute() returns the affected row count; zero means no match.
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return {"message": f"Session {session_id} deleted"}
