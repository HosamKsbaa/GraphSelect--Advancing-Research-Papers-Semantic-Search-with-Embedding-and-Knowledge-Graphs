# TC-06: Test Cases for Literature Synthesis

## Test Summary
- **Use Case**: UC-06
- **Total Tests**: 5
- **Passed**: 0
- **Failed**: 0
- **Blocked**: 0
- **Coverage**: 0%

## Test Cases

### TC-06-01: Successful Synthesis Generation
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: GroupedResults with 3 research questions, each having 8–12 ranked papers with abstracts
- **Expected**: Gemini generates a structured literature review with per-question sections (300–800 words each). All inline citations reference valid DOIs from the session graph. Output is valid Markdown.
- **Actual**: —
- **Notes**: Verify Gemini prompt includes structured output instructions and citation format requirements

### TC-06-02: Citation Validation
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: Generated synthesis text containing 15 inline citations (DOIs)
- **Expected**: System validates each DOI against Neo4j session graph. All 15 DOIs found. Validation report: `{ "total": 15, "valid": 15, "invalid": 0 }`.
- **Actual**: —
- **Notes**: Invalid citations should be flagged with `[CITATION NOT FOUND]` annotation

### TC-06-03: Hallucinated Citation Detection
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: Gemini-generated text with 1 fabricated DOI (`10.9999/fake.2024.0001`) not in the session graph
- **Expected**: System detects the invalid DOI. Citation is removed or flagged. Warning annotation added to the review. Validation report shows `invalid: 1`.
- **Actual**: —
- **Notes**: Critical safety check — hallucinated citations undermine review credibility

### TC-06-04: Gemini API Failure During Synthesis
- **Type**: Integration
- **Status**: [ ] Pending
- **Input**: Trigger synthesis with Gemini API returning HTTP 500 on first call
- **Expected**: System retries 3 times. If persistent, partial review returned with failed sections marked as `[Generation Failed — Retry Later]`. No crash.
- **Actual**: —
- **Notes**: Partial reviews should still be saveable and re-generatable per section

### TC-06-05: Single Paper Per Question Group
- **Type**: Unit
- **Status**: [ ] Pending
- **Input**: Research question group with only 1 paper
- **Expected**: System generates a brief summary (150–300 words) instead of a comparative synthesis. No comparative language used (e.g., "studies agree/disagree"). Citation to the single paper is valid.
- **Actual**: —
- **Notes**: Prompt template should switch to "summarize" mode when paper count is 1
