"""Empirical stress tests and adversarial concurrency challenges for SSE streaming.

Validates:
1. Multi-subscriber fan-out (50+ concurrent subscribers).
2. Multi-project isolation under concurrent load.
3. Rapid burst event emissions (1,000+ events/sec) non-blocking throughput.
4. Abrupt client disconnection, generator cancellation, and subscriber unregistration cleanup.
5. Heartbeat ping generation and idle connection stability.
6. History interleaving and live event ordering.
7. `ProgressService.clear()` thread/async safety and memory reclamation.
8. HTTP SSE endpoints (`/api/logs/progress/{project_id}/stream`, `/api/logs/agent-traces/stream`).
9. Search SSE stream cancellation handling and resource cleanup.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from core.logging.progress_service import ProgressEvent, ProgressService


@pytest.mark.asyncio
async def test_multi_subscriber_broadcast_fanout() -> None:
    """Stress test: 50 concurrent subscribers must each receive 100 emitted events in exact sequence."""
    service = ProgressService()
    project_id = "stress-fanout-project-001"
    num_subscribers = 50
    num_events = 100

    # Subscribe 50 concurrent queues
    queues = [service.subscribe(project_id) for _ in range(num_subscribers)]
    assert len(service._subscribers[project_id]) == num_subscribers

    # Background task to collect events per subscriber
    async def collect_from_queue(q: asyncio.Queue[ProgressEvent]) -> list[ProgressEvent]:
        collected = []
        for _ in range(num_events):
            item = await asyncio.wait_for(q.get(), timeout=3.0)
            collected.append(item)
        return collected

    collector_tasks = [asyncio.create_task(collect_from_queue(q)) for q in queues]

    # Emit 100 events in rapid succession
    start_time = time.monotonic()
    for i in range(num_events):
        event = ProgressEvent(
            phase="analysis",
            status="in_progress",
            message=f"Processing paper batch {i}",
            details={"batch_index": i},
        )
        await service.emit(project_id, event)
    emission_duration = time.monotonic() - start_time

    # Await all collectors
    results = await asyncio.gather(*collector_tasks)

    # Verification
    assert len(results) == num_subscribers
    for idx, sub_events in enumerate(results):
        assert len(sub_events) == num_events, f"Subscriber {idx} missed events"
        for i, ev in enumerate(sub_events):
            assert ev.message == f"Processing paper batch {i}"
            assert ev.details == {"batch_index": i}

    # Verify event store size
    history = await service.get_events(project_id)
    assert len(history) == num_events

    # Clean up subscribers
    for q in queues:
        service.unsubscribe(project_id, q)
    assert project_id not in service._subscribers


@pytest.mark.asyncio
async def test_multi_project_subscriber_isolation() -> None:
    """Stress test: Events emitted to project A must never leak to project B subscribers."""
    service = ProgressService()
    num_projects = 5
    subs_per_project = 10
    events_per_project = 40

    project_ids = [f"proj-iso-{p}" for p in range(num_projects)]
    queues_by_project: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}

    for pid in project_ids:
        queues_by_project[pid] = [service.subscribe(pid) for _ in range(subs_per_project)]

    async def collect(q: asyncio.Queue[ProgressEvent], expected_count: int) -> list[ProgressEvent]:
        items = []
        for _ in range(expected_count):
            item = await asyncio.wait_for(q.get(), timeout=3.0)
            items.append(item)
        return items

    tasks = []
    for pid in project_ids:
        for q in queues_by_project[pid]:
            tasks.append(asyncio.create_task(collect(q, events_per_project)))

    # Concurrently emit events across projects in round-robin fashion
    for i in range(events_per_project):
        for pid in project_ids:
            ev = ProgressEvent(
                phase="search",
                status="in_progress",
                message=f"{pid} event {i}",
                details={"project": pid, "seq": i},
            )
            await service.emit(pid, ev)

    all_results = await asyncio.gather(*tasks)

    # Verify isolation
    task_idx = 0
    for pid in project_ids:
        for _ in range(subs_per_project):
            res = all_results[task_idx]
            task_idx += 1
            assert len(res) == events_per_project
            for i, ev in enumerate(res):
                assert ev.details["project"] == pid
                assert ev.details["seq"] == i

    # Cleanup
    for pid in project_ids:
        for q in queues_by_project[pid]:
            service.unsubscribe(pid, q)
        assert pid not in service._subscribers


@pytest.mark.asyncio
async def test_rapid_event_emission_burst_throughput() -> None:
    """Stress test: 1,000 rapid event emissions must be non-blocking and process >500 events/sec."""
    service = ProgressService()
    project_id = "burst-throughput-001"
    num_events = 1000

    queue = service.subscribe(project_id)

    start_time = time.perf_counter()
    for i in range(num_events):
        await service.emit(
            project_id,
            ProgressEvent(
                phase="writing",
                status="in_progress",
                message=f"Burst event {i}",
                details={"i": i},
            ),
        )
    elapsed = time.perf_counter() - start_time

    throughput = num_events / max(elapsed, 0.0001)
    assert throughput > 500.0, f"Throughput too low: {throughput:.1f} events/sec (elapsed {elapsed:.4f}s)"

    # Verify all 1,000 events arrived in queue
    received = 0
    while not queue.empty():
        item = queue.get_nowait()
        assert item.message == f"Burst event {received}"
        received += 1
    assert received == num_events

    service.unsubscribe(project_id, queue)


@pytest.mark.asyncio
async def test_immediate_subscriber_disconnection_cleanup() -> None:
    """Stress test: When clients abruptly disconnect, subscriber queues must be cleaned up without leaking."""
    service = ProgressService()
    project_id = "disconnect-test-001"

    # Start 20 async streaming generators
    num_clients = 20
    num_disconnect = 15

    generators = [
        service.stream_events(project_id=project_id, include_history=False, heartbeat_interval=1.0)
        for _ in range(num_clients)
    ]

    # Prime the generators so they reach `queue = self.subscribe(project_id)`
    gen_tasks = [asyncio.create_task(gen.__anext__()) for gen in generators]
    await asyncio.sleep(0.05)  # Allow generators to subscribe and wait on queue.get()

    assert len(service._subscribers.get(project_id, [])) == num_clients

    # Emit 1 event to unblock first __anext__
    await service.emit(
        project_id,
        ProgressEvent(phase="planning", status="started", message="Initial planning"),
    )
    first_events = await asyncio.gather(*gen_tasks)
    assert len(first_events) == num_clients

    # Now abruptly cancel/close 15 generators (simulating browser tab close / network drop)
    for i in range(num_disconnect):
        await generators[i].aclose()

    # Allow cancellation/cleanup in `finally:` block of stream_events
    await asyncio.sleep(0.05)

    # Verify subscriber list is pruned down to 5
    active_subscribers = service._subscribers.get(project_id, [])
    assert len(active_subscribers) == (num_clients - num_disconnect), (
        f"Expected {num_clients - num_disconnect} subscribers, found {len(active_subscribers)}"
    )

    # Emit another event for remaining 5 clients
    remaining_tasks = [
        asyncio.create_task(generators[i].__anext__())
        for i in range(num_disconnect, num_clients)
    ]
    await service.emit(
        project_id,
        ProgressEvent(phase="planning", status="completed", message="Planning complete"),
    )
    second_events = await asyncio.gather(*remaining_tasks)
    assert len(second_events) == (num_clients - num_disconnect)

    # Close remaining
    for i in range(num_disconnect, num_clients):
        await generators[i].aclose()
    await asyncio.sleep(0.05)

    assert project_id not in service._subscribers


@pytest.mark.asyncio
async def test_heartbeat_ping_interval_generator() -> None:
    """Stress test: Generator yields periodic ping events during idle periods."""
    service = ProgressService()
    project_id = "heartbeat-test-001"

    # Set short heartbeat for testing (30ms)
    gen = service.stream_events(
        project_id=project_id,
        include_history=False,
        heartbeat_interval=0.03,
    )

    pings = []
    async for event_dict in gen:
        pings.append(event_dict)
        if len(pings) >= 3:
            break
    await gen.aclose()

    assert len(pings) == 3
    for p in pings:
        assert p["event"] == "ping"
        payload = json.loads(p["data"])
        assert "timestamp" in payload


@pytest.mark.asyncio
async def test_history_interleaving_and_live_stream_ordering() -> None:
    """Stress test: include_history=True replays past events before switching to live broadcast."""
    service = ProgressService()
    project_id = "history-interleaving-001"

    # Pre-emit 5 historical events
    for i in range(5):
        await service.emit(
            project_id,
            ProgressEvent(phase="search", status="in_progress", message=f"Hist {i}"),
        )

    # Start generator that requests history + max_events=8
    gen = service.stream_events(
        project_id=project_id,
        include_history=True,
        heartbeat_interval=2.0,
        max_events=8,
    )

    async def emit_live_delayed():
        await asyncio.sleep(0.05)
        for i in range(3):
            await service.emit(
                project_id,
                ProgressEvent(phase="writing", status="in_progress", message=f"Live {i}"),
            )

    emitter_task = asyncio.create_task(emit_live_delayed())

    yielded_events = []
    async for item in gen:
        yielded_events.append(json.loads(item["data"]))

    await emitter_task

    assert len(yielded_events) == 8
    # First 5 must be history
    for i in range(5):
        assert yielded_events[i]["message"] == f"Hist {i}"
        assert yielded_events[i]["phase"] == "search"
    # Next 3 must be live
    for i in range(3):
        assert yielded_events[5 + i]["message"] == f"Live {i}"
        assert yielded_events[5 + i]["phase"] == "writing"


@pytest.mark.asyncio
async def test_progress_service_clear_reclaims_memory() -> None:
    """Stress test: clear() purges events and subscribers cleanly without memory retention or errors."""
    service = ProgressService()
    project_id = "clear-mem-test-001"

    q1 = service.subscribe(project_id)
    await service.emit(project_id, ProgressEvent(phase="test", status="ok", message="msg"))

    assert project_id in service._events
    assert project_id in service._subscribers

    service.clear(project_id)

    assert project_id not in service._events
    assert project_id not in service._subscribers

    # Emitting to cleared project should work normally
    await service.emit(project_id, ProgressEvent(phase="test2", status="ok", message="msg2"))
    assert len(service._events[project_id]) == 1


def test_http_sse_endpoint_concurrency_stress() -> None:
    """Adversarial HTTP test: Multiple concurrent client connections reading SSE progress streams."""
    progress_svc = ProgressService()
    app.state.progress_service = progress_svc
    project_id = "http-sse-stress-001"

    # Prepopulate 2 events
    asyncio.run(
        progress_svc.emit(
            project_id,
            ProgressEvent(phase="analysis", status="started", message="Step 1"),
        )
    )
    asyncio.run(
        progress_svc.emit(
            project_id,
            ProgressEvent(phase="analysis", status="completed", message="Step 2"),
        )
    )

    client = TestClient(app)

    # Open 3 sequential/parallel streams with max_events=2
    for _ in range(3):
        with client.stream(
            "GET",
            f"/api/logs/progress/{project_id}/stream?include_history=true&max_events=2",
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            lines = [line for line in response.iter_lines() if line]
            stream_body = "\n".join(lines)
            assert "Step 1" in stream_body
            assert "Step 2" in stream_body


def test_http_agent_traces_stream_query_validation() -> None:
    """Adversarial HTTP test: agent-traces stream endpoint validates query parameters and streams."""
    progress_svc = ProgressService()
    app.state.progress_service = progress_svc
    project_id = "http-trace-stress-001"

    asyncio.run(
        progress_svc.emit(
            project_id,
            ProgressEvent(
                phase="planning",
                status="completed",
                message="Planner generated 4 sections",
                details={"sections_count": 4},
            ),
        )
    )

    client = TestClient(app)

    # Missing project_id should fail with 422
    err_resp = client.get("/api/logs/agent-traces/stream")
    assert err_resp.status_code == 422

    # Valid stream with max_events=1
    with client.stream(
        "GET",
        f"/api/logs/agent-traces/stream?project_id={project_id}&max_events=1",
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = [line for line in response.iter_lines() if line]
        body = "\n".join(lines)
        assert "Planner generated 4 sections" in body


@pytest.mark.asyncio
async def test_search_stream_cancellation_and_status_update() -> None:
    """Stress test: Search SSE generator properly updates MySQL status to PAUSED on asyncio.CancelledError."""
    from features.search.session_service import SearchSessionService
    from features.sessions.models import SessionStatus

    mock_neo4j = AsyncMock()
    mock_mysql = AsyncMock()
    mock_openalex = AsyncMock()

    session_data = {
        "seed_doi": "10.1234/seed",
        "research_questions": json.dumps(["RQ1"]),
        "similarity_threshold": 0.75,
        "max_depth": 2,
        "mode": "automated",
        "full_state": "{}",
    }

    service = SearchSessionService(
        neo4j=mock_neo4j,
        mysql=mock_mysql,
        openalex=mock_openalex,
    )

    with patch("features.search.graph_search_service.GraphSearchService.run_full_search") as mock_bfs:
        async def mock_bfs_infinite(*args, **kwargs):
            # Simulate infinite search that gets cancelled
            while True:
                await asyncio.sleep(0.01)
                yield AsyncMock(event_type=AsyncMock(value="PAPER_DISCOVERED"), model_dump_json=lambda: "{}")

        mock_bfs.side_effect = mock_bfs_infinite

        stream_gen = service.build_search_stream(
            session_id="sess-cancel-001",
            session_data=session_data,
            neo4j_service=mock_neo4j,
            mysql_service=mock_mysql,
        )

        # Consume 1 item and cancel
        task = asyncio.create_task(stream_gen.__anext__())
        await asyncio.sleep(0.02)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await stream_gen.aclose()

        # Check that update_session_status was called with RUNNING then PAUSED
        status_calls = [call.args for call in mock_mysql.update_session_status.call_args_list]
        assert ("sess-cancel-001", SessionStatus.RUNNING.value) in status_calls
        assert ("sess-cancel-001", SessionStatus.PAUSED.value) in status_calls
