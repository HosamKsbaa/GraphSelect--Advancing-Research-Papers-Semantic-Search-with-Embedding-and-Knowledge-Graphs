# TC-07: Test Cases for Session Management

## Test Summary
- **Use Case**: UC-07
- **Total Tests**: 6
- **Passed**: 3
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 50%

## Test Cases

### TC-07-01: List All Sessions
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: `GET /sessions` with 3 existing sessions in Neo4j
- **Expected**: HTTP 200 with array of 3 session summaries. Each summary contains `id`, `seed_title`, `created_at`, `paper_count`, `status`.
- **Actual**: Returns 3 sessions sorted by `created_at` descending. All metadata fields present and accurate.
- **Notes**: Verified against direct Neo4j query `MATCH (s:SearchSession) RETURN s ORDER BY s.created_at DESC`

### TC-07-02: Get Session Details
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: `GET /sessions/{id}` with a valid session ID
- **Expected**: HTTP 200 with full session data including seed paper, configuration (depth, mode), paper list with scores, and status.
- **Actual**: Returns complete session object. Paper list includes DOIs, titles, similarity scores, and hybrid scores where available.
- **Notes**: Response size scales with paper count — 500-paper session returns ~150KB JSON

### TC-07-03: Delete Session
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: `DELETE /sessions/{id}` with a valid completed session ID
- **Expected**: HTTP 204 No Content. Session node removed from Neo4j. Exclusive papers and edges cleaned up. Shared papers preserved.
- **Actual**: Session deleted. Verified via `MATCH (s:SearchSession {id: "{id}"}) RETURN count(s)` = 0. Shared papers confirmed present.
- **Notes**: Cascade delete uses Cypher `DETACH DELETE` with shared-node preservation logic

### TC-07-04: Session Not Found
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: `GET /sessions/nonexistent-uuid-1234`
- **Expected**: HTTP 404 with body `{ "error": "Session not found", "session_id": "nonexistent-uuid-1234" }`
- **Actual**: —
- **Notes**: Verify 404 is returned for all CRUD operations (GET, DELETE) with invalid IDs

### TC-07-05: Delete In-Progress Session
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: `DELETE /sessions/{id}` where session has `status: "crawling"`
- **Expected**: HTTP 409 Conflict with body `{ "error": "Cannot delete a session that is currently running", "suggestion": "Stop the search first" }`
- **Actual**: —
- **Notes**: Must verify session status check happens before any delete logic

### TC-07-06: Export Session Results
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: `GET /sessions/{id}/export?format=csv` with a completed session containing 100 ranked papers
- **Expected**: HTTP 200 with CSV attachment. Columns: `rank`, `doi`, `title`, `authors`, `year`, `similarity_score`, `pagerank_score`, `hybrid_score`, `research_question`.
- **Actual**: —
- **Notes**: Export should handle large sessions via streaming. Verify CSV encoding (UTF-8 BOM for Excel compatibility).
