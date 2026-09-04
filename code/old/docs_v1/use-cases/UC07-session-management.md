# UC-07: Session Management

## Overview
- **Actor**: Researcher
- **Priority**: P3
- **Status**: 🟡 In Progress (basic CRUD done)
- **Phase**: Phase 9

## Description
The researcher can save, load, view, delete, and export search sessions. Each session captures the complete state of a literature search including the seed paper, BFS configuration, crawled papers, citation graph, similarity scores, rankings, and (optionally) the generated literature review. Sessions are persisted in Neo4j as SearchSession nodes linked to all associated data.

## Preconditions
- Backend API server is running
- Neo4j database is accessible
- At least one search session exists (for load/view/delete operations)

## Main Flow
1. **List sessions**: Researcher sends `GET /sessions`
   - Backend returns a list of all sessions with summary metadata (ID, seed title, date, paper count, status)
2. **View session details**: Researcher sends `GET /sessions/{id}`
   - Backend returns full session data including configuration, paper list, and status
3. **Delete session**: Researcher sends `DELETE /sessions/{id}`
   - Backend removes the SearchSession node and all exclusively-linked data from Neo4j
   - Papers shared with other sessions are preserved (only the HAS_PAPER link is removed)
4. **Save session** (automatic): Session is auto-saved at each BFS level completion and at pipeline end
5. **Export results**: Researcher requests an export of ranked results
   - Backend generates a structured export (JSON/CSV) of the session's ranked papers

## Alternative Flows
- **AF-01: Session not found** — `GET /sessions/{id}` with invalid ID returns HTTP 404 with error message.
- **AF-02: Delete in-progress session** — Researcher attempts to delete a session that's currently running a search. System rejects with HTTP 409 Conflict and suggests stopping the search first.
- **AF-03: Concurrent session access** — Two researchers access the same session. Read operations proceed normally; write operations use optimistic locking via a version field.
- **AF-04: Large session export** — Session has >1000 papers. Export is streamed rather than buffered to avoid memory issues.

## Postconditions
- Session state is persisted in Neo4j and recoverable across server restarts
- Deleted sessions have all exclusive data cleaned up (no orphan nodes)
- Export files are generated and downloadable by the researcher
- Session list reflects the current state of all sessions

## Related Diagrams
- [Neo4j Schema Diagram](../diagrams/neo4j_schema.puml)
- [API Flow Diagram](../diagrams/api_flow.puml)

## Related Test Cases
- [TC-07: Session Management Tests](../test-cases/TC07-session-management.md)
