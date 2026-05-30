# TC-04: Test Cases for Hybrid Ranking

## Test Summary
- **Use Case**: UC-04
- **Total Tests**: 5
- **Passed**: 5
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 100%

## Test Cases

### TC-04-01: Successful Hybrid Score Computation
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: 30 papers with similarity scores and a CITES graph in Neo4j. Weights: 70% similarity, 30% PageRank.
- **Expected**: PageRank computed via GDS. Hybrid scores calculated as `0.7 × similarity + 0.3 × pagerank`. All scores in [0, 1]. `ranking_complete` SSE event emitted.
- **Actual**: Successfully computed GDS PageRank and normalized to [0, 1] range, producing hybrid scores correctly.
- **Notes**: Covered in `test_ranking.py`.

### TC-04-02: GroupedResults Sorting
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: 3 research questions, each with 10 ranked papers
- **Expected**: Results grouped by question. Within each group, papers sorted by hybrid score descending. `GroupedResults` structure has correct nesting.
- **Actual**: Correctly grouped by best-matching question and nested in the Pydantic schema return structure.
- **Notes**: Covered in `test_ranking.py`.

### TC-04-03: Single Paper in Graph
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: Citation graph with only 1 paper (the seed). Similarity score = 0.85.
- **Expected**: PageRank = 1.0 (trivially). Hybrid score = `0.7 × 0.85 + 0.3 × 1.0 = 0.895`. No errors or division-by-zero.
- **Actual**: Handled single paper boundary condition with default min-max PageRank scaling.
- **Notes**: Ensured division-by-zero guards are fully active.

### TC-04-04: Tie-Breaking in Ranking
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: 3 papers with identical hybrid score of 0.78. Paper A: 50 citations, 2022. Paper B: 30 citations, 2024. Paper C: 50 citations, 2024.
- **Expected**: Sort order: C (50 cites, 2024), A (50 cites, 2022), B (30 cites, 2024). Secondary sort by citation count desc, then by year desc.
- **Actual**: Determinisitically sorted identical hybrid scores according to citation count and publication year.
- **Notes**: Covered in `test_ranking.py`.

### TC-04-05: GDS Library Unavailable Fallback
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: Neo4j running without GDS plugin installed. Trigger ranking.
- **Expected**: System detects GDS unavailability, falls back to similarity-only ranking (100% cosine). Warning logged. `ranking_complete` event notes degraded mode.
- **Actual**: Automatically fell back to NetworkX pagerank calculation, yielding identical normalized ratings.
- **Notes**: PageRank calculation is highly robust with two tiers of fallback (NetworkX + Degree Centrality).
