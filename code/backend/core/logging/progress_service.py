"""Progress event tracking for ALRS v2 agentic workflows.

Provides a lightweight event bus for tracking pipeline phase progress
(e.g. planning, searching, analysis, writing). Events are stored in
memory per project and can be queried by phase or streamed in real time via SSE.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

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
    """In-memory progress event store and real-time SSE stream bus for pipeline observability.

    Events are organized by project_id and can be filtered by phase or streamed via SSE.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[ProgressEvent]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue[ProgressEvent]:
        """Subscribe to live progress events for a project."""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        if project_id not in self._subscribers:
            self._subscribers[project_id] = []
        self._subscribers[project_id].append(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        """Unsubscribe a queue from project progress events."""
        if project_id in self._subscribers:
            try:
                self._subscribers[project_id].remove(queue)
                if not self._subscribers[project_id]:
                    del self._subscribers[project_id]
            except ValueError:
                pass

    async def emit(
        self,
        project_id: str,
        event: ProgressEvent,
    ) -> None:
        """Record a progress event for a project and broadcast to active stream subscribers.

        Args:
            project_id: UUID of the project.
            event: The progress event to record.
        """
        if project_id not in self._events:
            self._events[project_id] = []
        self._events[project_id].append(event)
        logger.info(
            "[%s] %s/%s: %s",
            project_id[:8] if project_id else "global",
            event.phase,
            event.status,
            event.message,
        )

        # Broadcast to live subscribers
        subscribers = self._subscribers.get(project_id, [])
        for queue in list(subscribers):
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.debug("Failed to put event into subscriber queue: %s", exc)

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

    async def stream_events(
        self,
        project_id: str,
        include_history: bool = True,
        heartbeat_interval: float = 15.0,
        max_events: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream progress events for a project as an SSE-formatted dictionary generator.

        Yields:
            Dict matching `{"event": "progress", "data": ...}` or `{"event": "ping", "data": ...}`.
        """
        count = 0
        # Yield historical events if requested
        if include_history:
            history = await self.get_events(project_id)
            for ev in history:
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "phase": ev.phase,
                        "status": ev.status,
                        "message": ev.message,
                        "timestamp": ev.timestamp.isoformat(),
                        "details": ev.details,
                    }),
                }
                count += 1
                if max_events is not None and count >= max_events:
                    return

        queue = self.subscribe(project_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "phase": event.phase,
                            "status": event.status,
                            "message": event.message,
                            "timestamp": event.timestamp.isoformat(),
                            "details": event.details,
                        }),
                    }
                    count += 1
                    if max_events is not None and count >= max_events:
                        break
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": datetime.now(tz=timezone.utc).isoformat()}),
                    }
        except asyncio.CancelledError:
            logger.info("SSE client disconnected for project %s", project_id)
        finally:
            self.unsubscribe(project_id, queue)

    def clear(self, project_id: str) -> None:
        """Clear all events and subscribers for a project.

        Args:
            project_id: UUID of the project.
        """
        self._events.pop(project_id, None)
        self._subscribers.pop(project_id, None)
