# UC-05: SSE Progress Streaming

## Overview
- **Actor**: Researcher (passive viewer)
- **Priority**: P2
- **Status**: 🟡 In Progress
- **Phase**: Phase 5

## Description
The researcher receives real-time Server-Sent Events (SSE) during the BFS citation crawl, semantic filtering, and ranking phases. The SSE stream provides progress percentage, current level information, discovered paper counts, error recovery notifications, and throttling alerts. The system defines 9 distinct event types that cover the full lifecycle of a search operation, giving the researcher complete visibility into the pipeline's progress.

## Preconditions
- A search has been initiated (POST /start called)
- SSE connection is established via GET /stream
- Backend event emitter is active for the current session

## Main Flow
1. Researcher initiates a search, which triggers an SSE stream
2. Frontend opens an `EventSource` connection to `GET /stream?session_id={id}`
3. Backend emits events through the following lifecycle:
   a. `search_started` — Emitted once when BFS begins, includes session ID and seed paper info
   b. `level_complete` — Emitted after each BFS level, includes level number, papers found, cumulative count
   c. `embedding_progress` — Emitted during embedding generation, includes batch progress percentage
   d. `cycle_results` — Emitted after each BFS cycle with intermediate paper data
   e. `ranking_complete` — Emitted when hybrid ranking finishes, includes top-N summary
   f. `search_complete` — Emitted once when the entire pipeline finishes, includes final stats
   g. `error_recovered` — Emitted when a transient error is caught and recovered from
   h. `search_failed` — Emitted on unrecoverable failure, includes error details
   i. `throttled` — Emitted when OpenAlex rate limiting is active, includes retry delay
4. Frontend parses each event and updates the progress UI accordingly
5. On `search_complete` or `search_failed`, the SSE connection is closed

## Alternative Flows
- **AF-01: SSE connection dropped** — Network interruption causes the EventSource to disconnect. Frontend auto-reconnects using `Last-Event-ID` header. Backend replays missed events from the event buffer.
- **AF-02: Multiple browser tabs** — Researcher opens the same session in multiple tabs. Each tab gets its own SSE connection and receives identical events.
- **AF-03: Backend restart during search** — Backend crashes mid-search. Upon restart, the session state is recovered and a `error_recovered` event is emitted with recovery context.
- **AF-04: Long-running search** — Search exceeds 30 minutes. System continues emitting keepalive comments (`:keepalive`) every 30 seconds to prevent proxy timeout.

## Postconditions
- Researcher has received a complete event log of the search lifecycle
- All 9 event types have been emitted as appropriate for the search
- Frontend UI reflects the final state (complete or failed) of the search
- Event history is retained in memory for reconnection replay

## Related Diagrams
- [SSE Events Diagram](../diagrams/sse_events.puml)
- [API Flow Diagram](../diagrams/api_flow.puml)

## Related Test Cases
- [TC-05: SSE Progress Streaming Tests](../test-cases/TC05-sse-progress-streaming.md)
