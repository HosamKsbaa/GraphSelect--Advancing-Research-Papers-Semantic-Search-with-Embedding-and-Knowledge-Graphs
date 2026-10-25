# Gemini embeddings reference

Checked against Google's [official embedding documentation](https://ai.google.dev/gemini-api/docs/embeddings) on 2026-10-10.

## Current ALRS profile

- Model: `gemini-embedding-2`; dimensions: 768; profile: `gemini-embedding-2:768:retrieval-v1`.
- Query text: `task: search result | query: {question}`.
- Document text: `title: {title} | text: {abstract}`.
- Do not send `task_type` to this model or reuse the old model's prefixes.
- Use one native SDK content object per independent text input. Multiple parts can aggregate into one vector.
- Request 768 dimensions. Validate finite values and normalize before storage. Embedding 2 already normalizes reduced dimensions; explicit normalization verifies the application contract.
- Never compare embeddings from different models or formatting versions.

## Application rules

Implemented in `code/engines/embeddings/` (use `query_text()` and `document_text()` for the formats above).

Create the asynchronous SDK client once at startup and pass it in. Apply timeouts and no automatic retry. Engines currently keep vectors in memory; Neo4j storage is planned for M2. Do not log vectors or place them in checkpoints, SSE events, operation snapshots, or traces. Reuse a vector only when DOI, content hash, model, dimensions, and format version match. Missing or oversized abstracts remain saved and unranked; never truncate silently.

Embeddings cover text abstracts only, not PDFs, images, video, or audio. Background on this contract: [full-alrs-search decision](../../../brain/decisions/full-alrs-search.md) (in the parent MasterProject2 workspace).
