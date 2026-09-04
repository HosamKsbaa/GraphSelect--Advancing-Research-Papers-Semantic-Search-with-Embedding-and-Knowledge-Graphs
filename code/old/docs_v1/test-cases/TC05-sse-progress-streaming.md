# TC-05: Test Cases for SSE Progress Streaming

## Test Summary
- **Use Case**: UC-05
- **Total Tests**: 5
- **Passed**: 2
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 40%

## Test Cases

### TC-05-01: Full Event Lifecycle
- **Type**: E2E
- **Status**: [x] Passed
- **Input**: Start a BFS crawl and listen on `GET /stream?session_id={id}` via EventSource
- **Expected**: Events received in order: `search_started` → N × `level_complete` → `search_complete`. Each event has valid JSON data payload with `event`, `data`, and `id` fields.
- **Actual**: All events received in correct order. `search_started` includes session ID and seed DOI. `level_complete` events include level number and paper count. `search_complete` includes final totals.
- **Notes**: Verified event ordering is deterministic and consistent across multiple runs

### TC-05-02: SSE Reconnection with Last-Event-ID
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: Start SSE stream, forcibly disconnect after 3 events, reconnect with `Last-Event-ID` header
- **Expected**: Backend replays missed events from the buffer. No duplicate events. Stream resumes from the correct point.
- **Actual**: Reconnection works. Missed events replayed correctly. No duplicates observed in the frontend log.
- **Notes**: Event buffer retains last 100 events per session for replay

### TC-05-03: Error Recovery Event
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: Trigger a transient OpenAlex error during BFS crawl
- **Expected**: `error_recovered` event emitted with `{ "error_type": "openalex_timeout", "retry_count": 2, "message": "Recovered after 2 retries" }`. Crawl continues after recovery.
- **Actual**: —
- **Notes**: Need to simulate transient API errors in test environment

### TC-05-04: Throttled Event
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: Trigger OpenAlex rate limiting (HTTP 429) during BFS crawl
- **Expected**: `throttled` event emitted with `{ "retry_after_seconds": 1, "message": "Rate limited by OpenAlex, waiting 1s" }`. Crawl resumes after delay.
- **Actual**: —
- **Notes**: Requires controlled test environment or mock to reliably trigger rate limits

### TC-05-05: Keepalive During Long Searches
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: Start a deep BFS crawl (depth 4+) that takes >60 seconds
- **Expected**: SSE keepalive comments (`:keepalive\n\n`) emitted every 30 seconds. EventSource connection stays alive through proxies.
- **Actual**: —
- **Notes**: Keepalive prevents Nginx/CloudFlare/reverse proxy from closing idle connections
