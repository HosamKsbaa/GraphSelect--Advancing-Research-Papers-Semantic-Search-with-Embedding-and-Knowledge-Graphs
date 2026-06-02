"""Progress event tracking for ALRS v2 agentic workflows.

Provides a lightweight event bus for tracking pipeline phase progress
(e.g. planning, searching, analysis, writing). Events are stored in
memory per project and can be queried by phase.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProgressEvent(BaseModel):
    """A single progress event emitted during a pipeline run."""

    phase: str = Field(..., description="Pipeline phase (e.g. 'planning', 'search', 'analysis', 'writing')")
    status: str = Field(..., description="Event status (e.g. 'started', 'in_progress', 'completed', 'failed')")
    message: str = Field(..., description="Human-readable progress message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    details: dict[str, object] | None = Field(default=None, description="Optional structured details")


class ProgressService:
    """In-memory progress event store for pipeline observability.

    Events are organized by project_id and can be filtered by phase.
    This is a lightweight solution; for production scale, events should
    be persisted to MySQL or streamed via SSE.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[ProgressEvent]] = {}

    async def emit(
        self,
        project_id: str,
        event: ProgressEvent,
    ) -> None:
        """Record a progress event for a project.

        Args:
            project_id: UUID of the project.
            event: The progress event to record.
        """
        if project_id not in self._events:
            self._events[project_id] = []
        self._events[project_id].append(event)
        logger.info(
            "[%s] %s/%s: %s",
            project_id[:8],
            event.phase,
            event.status,
            event.message,
        )

    async def get_events(
        self,
        project_id: str,
        phase: str | None = None,
    ) -> list[ProgressEvent]:
        """Retrieve progress events for a project, optionally filtered by phase.

        Args:
            project_id: UUID of the project.
            phase: Optional phase filter.

        Returns:
            List of matching ProgressEvent instances, ordered by timestamp.
        """
        events = self._events.get(project_id, [])
        if phase is not None:
            events = [e for e in events if e.phase == phase]
        return sorted(events, key=lambda e: e.timestamp)

    def clear(self, project_id: str) -> None:
        """Clear all events for a project.

        Args:
            project_id: UUID of the project.
        """
        self._events.pop(project_id, None)
