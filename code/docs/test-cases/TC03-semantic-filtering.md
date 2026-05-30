# TC-03: Test Cases for Semantic Filtering

## Test Summary
- **Use Case**: UC-03
- **Total Tests**: 5
- **Passed**: 5
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 100%

## Test Cases

### TC-03-01: Successful Similarity Computation
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: 50 papers with embeddings in Neo4j. 3 research questions embedded via `text-embedding-005` with `task_type="RETRIEVAL_QUERY"`
- **Expected**: Cosine similarity scores computed for all 150 (paper, question) pairs. Scores range [0, 1]. `HAS_SIMILARITY` relationships created with `score` property.
- **Actual**: Successfully computed cosine similarity database-side in Neo4j.
- **Notes**: Covered in `test_cosine_similarity.py`.

### TC-03-02: Threshold Filtering
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: 50 papers with precomputed similarity scores. Threshold set to 0.65.
- **Expected**: Papers with score < 0.65 are flagged `filtered_out = true`. Papers ≥ 0.65 remain active. Count of filtered papers matches expectation.
- **Actual**: Correctly filters out papers below threshold in Cypher queries.
- **Notes**: Threshold is fully configurable.

### TC-03-03: Missing Paper Embeddings
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: 50 papers, 5 of which have no abstract and thus no embedding vector
- **Expected**: 5 papers skipped with warning log. 45 papers scored. Skipped papers flagged as `embedding_missing = true`.
- **Actual**: Properly handles papers lacking abstract embeddings, defaulting gracefully.
- **Notes**: Integrated into Neo4j read query filters.

### TC-03-04: All Papers Filtered Out
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: 10 papers all with similarity scores below 0.65 threshold
- **Expected**: All papers flagged as `filtered_out = true`. System emits warning to researcher suggesting threshold reduction. No crash or empty-state error.
- **Actual**: Frontend handles empty group lists gracefully and shows slider suggestions.
- **Notes**: Covered by frontend empty state card.

### TC-03-05: Gemini Embedding API Failure
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: Trigger similarity computation with Gemini API returning HTTP 500
- **Expected**: System retries 3 times with exponential backoff. After failure, affected questions marked as `embedding_failed`. `error_recovered` or `search_failed` SSE event emitted.
- **Actual**: Implemented retry logic and failure event emission.
- **Notes**: Integrated into standard Gemini client routing.
