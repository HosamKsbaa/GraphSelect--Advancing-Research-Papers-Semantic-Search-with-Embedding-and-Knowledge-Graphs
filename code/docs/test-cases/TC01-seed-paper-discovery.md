# TC-01: Test Cases for Seed Paper Discovery

## Test Summary
- **Use Case**: UC-01
- **Total Tests**: 6
- **Passed**: 6
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 95%

## Test Cases

### TC-01-01: Successful Title Resolution
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: `POST /resolve-title` with body `{ "title": "Graph Neural Networks: A Review of Methods and Applications" }`
- **Expected**: HTTP 200 with array of candidate papers, each containing `title`, `authors`, `year`, `doi`, `citation_count`
- **Actual**: Returns 5–10 candidates ranked by relevance. Top result matches exact title with DOI `10.1016/j.aiopen.2021.01.001`
- **Notes**: OpenAlex returns results within 800ms on average

### TC-01-02: Select Seed Paper from Candidates
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: Researcher selects candidate with DOI `10.1145/3292500.3330919` from the returned list
- **Expected**: System stores the DOI, returns confirmation with paper metadata, session is initialized
- **Actual**: DOI stored successfully, session created with `status: seed_selected`
- **Notes**: Verified seed paper appears as the root node when BFS starts

### TC-01-03: No Results Found
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: `POST /resolve-title` with body `{ "title": "xyzzynonexistentpaper12345" }`
- **Expected**: HTTP 200 with empty array `[]` and message `"No papers found matching your query"`
- **Actual**: Returns empty array as expected with appropriate message
- **Notes**: Frontend displays "No papers found" UI state correctly

### TC-01-04: Empty Title Input
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: `POST /resolve-title` with body `{ "title": "" }`
- **Expected**: HTTP 400 with validation error `"Title cannot be empty"`
- **Actual**: Returns 400 with validation error as expected
- **Notes**: Frontend disables search button when input is empty (client-side validation)

### TC-01-05: OpenAlex API Timeout
- **Type**: Integration
- **Status**: [x] Passed
- **Input**: `POST /resolve-title` with simulated OpenAlex timeout (network delay >10s)
- **Expected**: System retries up to 3 times, then returns HTTP 503 with `"OpenAlex service temporarily unavailable"`
- **Actual**: Retry logic fires correctly. After 3 failed attempts, returns 503 with appropriate error
- **Notes**: Exponential backoff intervals: 1s, 2s, 4s. Total wait ~7s before failure response

### TC-01-06: Special Characters in Title
- **Type**: Unit
- **Status**: [x] Passed
- **Input**: `POST /resolve-title` with body `{ "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding" }`
- **Expected**: HTTP 200 with candidates matching the title despite the colon character
- **Actual**: Returns correct candidates. Colon and special characters handled properly in URL encoding
- **Notes**: Verified with titles containing colons, hyphens, parentheses, and Unicode characters
