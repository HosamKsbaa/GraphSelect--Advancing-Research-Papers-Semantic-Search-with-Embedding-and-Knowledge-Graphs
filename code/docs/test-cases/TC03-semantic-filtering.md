# TC-03: Test Cases for Semantic Filtering

## Test Summary
- **Use Case**: UC-03
- **Total Tests**: 5
- **Passed**: 0
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 0%

## Test Cases

### TC-03-01: Successful Similarity Computation
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: 50 papers with embeddings in Neo4j. 3 research questions embedded via `gemini-embedding-2` with prefix `task: search result | query: {question}`
- **Expected**: Cosine similarity scores computed for all 150 (paper, question) pairs. Scores range [0, 1]. `HAS_SIMILARITY` relationships created with `score` property.
- **Actual**: —
- **Notes**: Must verify embeddings use correct task prefix format per Gemini embedding guidelines

### TC-03-02: Threshold Filtering
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: 50 papers with precomputed similarity scores. Threshold set to 0.65.
- **Expected**: Papers with score < 0.65 are flagged `filtered_out = true`. Papers ≥ 0.65 remain active. Count of filtered papers matches expectation.
- **Actual**: —
- **Notes**: Threshold should be configurable per session

### TC-03-03: Missing Paper Embeddings
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: 50 papers, 5 of which have no abstract and thus no embedding vector
- **Expected**: 5 papers skipped with warning log. 45 papers scored. Skipped papers flagged as `embedding_missing = true`.
- **Actual**: —
- **Notes**: Papers without abstracts should still appear in results but with no similarity score

### TC-03-04: All Papers Filtered Out
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: 10 papers all with similarity scores below 0.65 threshold
- **Expected**: All papers flagged as `filtered_out = true`. System emits warning to researcher suggesting threshold reduction. No crash or empty-state error.
- **Actual**: —
- **Notes**: Frontend should display actionable guidance (e.g., "Try lowering the threshold to 0.50")

### TC-03-05: Gemini Embedding API Failure
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: Trigger similarity computation with Gemini API returning HTTP 500
- **Expected**: System retries 3 times with exponential backoff. After failure, affected questions marked as `embedding_failed`. `error_recovered` or `search_failed` SSE event emitted.
- **Actual**: —
- **Notes**: Must handle both transient (500, 503) and permanent (400, 401) API errors differently
