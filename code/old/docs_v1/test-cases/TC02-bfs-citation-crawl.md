# TC-02: Test Cases for BFS Citation Crawl

## Test Summary
- **Use Case**: UC-02
- **Total Tests**: 6
- **Passed**: 6
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 90%

## Test Cases

### TC-02-01: Successful Automated BFS Crawl (Depth 2)
- **Type**: E2E
- **Status**: [x] Passed
- **Input**: `POST /start` with body `{ "doi": "10.1145/3292500.3330919", "depth": 2, "mode": "automated" }`
- **Expected**: BFS traverses 2 levels. Papers and CITES edges stored in Neo4j. SSE events emitted for each level. `search_complete` event with final stats.
- **Actual**: Level 0 (seed): 1 paper. Level 1: 28 papers. Level 2: 312 papers. Total CITES edges: 487. Completed in ~45s.
- **Notes**: Verified Neo4j contains correct node count and edge directions via Cypher `MATCH (p:Paper)-[r:CITES]->(q:Paper) RETURN count(r)`

### TC-02-02: Interactive Mode with Selective Enqueuing
- **Type**: E2E
- **Status**: [x] Passed
- **Input**: `POST /start` with `{ "doi": "10.1145/3292500.3330919", "depth": 3, "mode": "interactive" }`. At level 1, select only 5 of 28 papers to enqueue.
- **Expected**: BFS pauses at level 1 with candidate list. After selection, only 5 papers are enqueued for level 2. Unselected papers marked as leaf nodes.
- **Actual**: Interactive pause works correctly. Selected 5 papers, level 2 discovered 47 papers (vs 312 in automated). Leaf nodes correctly flagged.
- **Notes**: Interactive mode significantly reduces graph size while maintaining researcher control

### TC-02-03: Duplicate DOI Handling
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: BFS crawl where paper A cites paper C and paper B also cites paper C (DOI `10.1145/3292500.3330919`)
- **Expected**: Paper C is stored once in Neo4j (MERGE/upsert). Both CITES edges (A→C, B→C) are created. No duplicate Paper nodes.
- **Actual**: Single Paper node exists for DOI. Two distinct CITES edges created. Verified via `MATCH (p:Paper {doi: "10.1145/3292500.3330919"}) RETURN count(p)` = 1
- **Notes**: Uses Cypher MERGE on DOI for idempotent upserts

### TC-02-04: OpenAlex Rate Limiting (HTTP 429)
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: BFS crawl with rapid sequential requests triggering OpenAlex's rate limit
- **Expected**: System receives HTTP 429, emits `throttled` SSE event with retry delay, backs off, and resumes crawl after delay
- **Actual**: Rate limit triggered at ~15 req/s. `throttled` event emitted with `retry_after: 1`. Crawl resumed after delay and completed successfully.
- **Notes**: Polite pool email header configured to increase rate limit allowance

### TC-02-05: Neo4j Connection Failure
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: BFS crawl with Neo4j service stopped mid-crawl (simulated)
- **Expected**: System retries 3 times, emits `search_failed` SSE event, saves partial progress to memory buffer
- **Actual**: Connection retry fires 3 times (1s, 2s, 4s intervals). `search_failed` event emitted with error details. Partial papers recoverable after Neo4j restart.
- **Notes**: Partial recovery tested — papers from completed levels are preserved

### TC-02-06: Empty Citation Network
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: `POST /start` with DOI of a very recent paper that has zero citations and zero references
- **Expected**: BFS completes immediately at level 0 with only the seed paper. `search_complete` event shows `total_papers: 1, total_edges: 0`.
- **Actual**: Completes in <1s. Single paper node in Neo4j. SSE events: `search_started` → `level_complete (level 0)` → `search_complete`
- **Notes**: Edge case handled gracefully — no errors or infinite loops
