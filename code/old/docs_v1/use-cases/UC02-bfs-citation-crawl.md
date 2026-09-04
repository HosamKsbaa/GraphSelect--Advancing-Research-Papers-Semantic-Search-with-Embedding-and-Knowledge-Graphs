# UC-02: BFS Citation Crawl

## Overview
- **Actor**: Researcher
- **Priority**: P1
- **Status**: 🟢 Complete
- **Phase**: Phase 3

## Description
The system crawls the citation network starting from the seed paper using a queue-based Breadth-First Search (BFS) algorithm. At each level, the system fetches referenced and citing works from OpenAlex, stores discovered papers and citation edges in Neo4j, and streams progress back to the researcher via SSE. The crawl supports two modes: automated (traverses all levels until depth limit) and interactive (pauses at each level for researcher review and selective enqueuing).

## Preconditions
- Seed paper has been selected (UC-01 complete)
- Neo4j database is running and accessible
- OpenAlex API is reachable
- SSE connection is established between frontend and backend

## Main Flow
1. Researcher initiates the search by clicking "Start Search"
2. Frontend sends `POST /start` with seed DOI, depth limit, and mode (automated/interactive)
3. Backend creates a BFS queue with the seed paper as the root node
4. **For each BFS level:**
   a. Dequeue all papers at the current level
   b. For each paper, fetch references and citations from OpenAlex
   c. Create Paper nodes and CITES edges in Neo4j
   d. Link all papers to the current SearchSession node
   e. Emit `level_complete` SSE event with level stats
   f. Enqueue newly discovered papers for the next level
5. Frontend receives progress via `GET /stream` (SSE endpoint)
6. BFS continues until depth limit is reached or no new papers are found
7. System emits `search_complete` SSE event with final statistics

## Alternative Flows
- **AF-01: Interactive mode** — At each level completion, the system pauses and presents discovered papers. Researcher selects which papers to enqueue for the next level. Unselected papers are marked as leaf nodes.
- **AF-02: OpenAlex rate limiting** — System receives HTTP 429. Implements backoff delay, emits `throttled` SSE event, and retries after the specified wait period.
- **AF-03: Duplicate DOI encountered** — A paper already exists in Neo4j for this session. System skips re-fetching but still creates the citation edge if it doesn't exist (idempotent upsert).
- **AF-04: Paper metadata missing** — OpenAlex returns incomplete data (no abstract, no authors). System stores available fields and marks the paper with a `metadata_incomplete` flag.
- **AF-05: Neo4j connection failure** — System retries connection 3 times. If persistent, emits `search_failed` SSE event and saves partial progress.

## Postconditions
- Complete citation graph stored in Neo4j up to the specified depth
- All Paper nodes linked to the SearchSession node via HAS_PAPER relationship
- All citation relationships stored as CITES edges with direction
- Session metadata updated with final paper count, edge count, and depth reached
- BFS traversal log available for debugging

## Related Diagrams
- [BFS Algorithm Diagram](../diagrams/bfs_algorithm.puml)
- [Neo4j Schema Diagram](../diagrams/neo4j_schema.puml)
- [SSE Events Diagram](../diagrams/sse_events.puml)

## Related Test Cases
- [TC-02: BFS Citation Crawl Tests](../test-cases/TC02-bfs-citation-crawl.md)
