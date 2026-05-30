# UC-03: Semantic Filtering

## Overview
- **Actor**: System (automated)
- **Priority**: P1
- **Status**: 🔴 Not Started
- **Phase**: Phase 4

## Description
The system embeds all research questions using the Gemini embedding model and computes cosine similarity between question embeddings and paper embeddings stored in Neo4j. Using the Neo4j Graph Data Science (GDS) library, the system performs efficient vector similarity computation at scale. Papers scoring below the configured similarity threshold are filtered out, ensuring only semantically relevant papers proceed to the ranking stage.

## Preconditions
- Citation graph has been crawled and papers are stored in Neo4j (UC-02 complete)
- Paper embeddings have been generated and stored as vector properties on Paper nodes
- Research questions have been defined by the researcher
- Neo4j GDS library is installed and available
- Gemini embedding API is accessible for question embedding

## Main Flow
1. System retrieves the researcher's list of research questions
2. System embeds each research question using `gemini-embedding-2` with task prefix `task: search result | query: {question}`
3. System stores question embeddings as vector properties on ResearchQuestion nodes in Neo4j
4. System creates a GDS vector similarity projection over Paper and ResearchQuestion nodes
5. For each research question:
   a. Compute cosine similarity between the question embedding and all paper embeddings via GDS
   b. Store similarity scores as `HAS_SIMILARITY` relationships (question → paper) with a `score` property
6. System applies the similarity threshold filter (default: 0.65)
7. Papers below the threshold are flagged as `filtered_out = true`
8. System emits `embedding_progress` SSE events during computation

## Alternative Flows
- **AF-01: Missing paper embeddings** — Some papers lack embeddings (e.g., no abstract available). System skips these papers and logs a warning. They are excluded from similarity scoring.
- **AF-02: Gemini API failure** — Embedding API call fails. System retries with exponential backoff (3 attempts). If persistent, marks affected questions as `embedding_failed` and emits an `error_recovered` or `search_failed` SSE event.
- **AF-03: All papers filtered out** — Every paper falls below the threshold. System warns the researcher and suggests lowering the threshold or broadening the research questions.
- **AF-04: GDS library unavailable** — Fallback to application-level cosine similarity computation (slower but functional).

## Postconditions
- Each paper has a cosine similarity score relative to each research question
- `HAS_SIMILARITY` relationships exist in Neo4j between ResearchQuestion and Paper nodes
- Papers below threshold are flagged but not deleted (reversible filtering)
- Similarity statistics (mean, median, distribution) are available for the session

## Related Diagrams
- [Neo4j Schema Diagram](../diagrams/neo4j_schema.puml)
- [Backend Classes Diagram](../diagrams/backend_classes.puml)

## Related Test Cases
- [TC-03: Semantic Filtering Tests](../test-cases/TC03-semantic-filtering.md)
