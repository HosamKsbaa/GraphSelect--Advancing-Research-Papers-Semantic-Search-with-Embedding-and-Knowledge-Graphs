# UC-04: Hybrid Ranking

## Overview
- **Actor**: System (automated)
- **Priority**: P1
- **Status**: 🔴 Not Started
- **Phase**: Phase 4

## Description
The system ranks papers using a hybrid scoring formula that combines semantic relevance (70% weight from cosine similarity) with structural importance (30% weight from PageRank computed over the citation graph). PageRank is calculated using the Neo4j Graph Data Science (GDS) library over the CITES relationship graph. Final results are grouped by research question, producing a `GroupedResults` structure sorted by hybrid score in descending order.

## Preconditions
- Semantic filtering is complete with similarity scores assigned (UC-03 complete)
- Citation graph exists in Neo4j with CITES edges
- Neo4j GDS library is installed and available
- At least one paper passes the similarity threshold

## Main Flow
1. System creates a GDS graph projection of Paper nodes and CITES relationships
2. System runs PageRank algorithm on the projected graph with default damping factor (0.85)
3. PageRank scores are normalized to [0, 1] range and stored as `pagerank` property on Paper nodes
4. For each non-filtered paper:
   a. Retrieve cosine similarity score per research question
   b. Retrieve normalized PageRank score
   c. Compute hybrid score: `hybrid = 0.7 × similarity + 0.3 × pagerank`
   d. Store hybrid score on the `HAS_SIMILARITY` relationship
5. System groups results by research question
6. Within each group, papers are sorted by hybrid score (descending)
7. System constructs `GroupedResults` response object
8. System emits `ranking_complete` SSE event with summary statistics

## Alternative Flows
- **AF-01: Single-paper graph** — Only one paper in the graph (the seed). PageRank is trivially 1.0. Hybrid score equals similarity score.
- **AF-02: Disconnected subgraphs** — Some papers have no citation links. Their PageRank defaults to the base value (1/N). System proceeds normally.
- **AF-03: GDS library unavailable** — Fallback to a simplified ranking using only cosine similarity (weight becomes 100%). System logs a warning about degraded ranking quality.
- **AF-04: Tie-breaking** — Papers with identical hybrid scores are secondary-sorted by citation count (descending), then by publication year (most recent first).

## Postconditions
- All non-filtered papers have a hybrid score computed and stored
- `GroupedResults` structure is available with papers sorted per research question
- PageRank scores are persisted on Paper nodes in Neo4j
- Ranking metadata (weights used, total papers ranked) stored on SearchSession

## Related Diagrams
- [Neo4j Schema Diagram](../diagrams/neo4j_schema.puml)
- [Backend Classes Diagram](../diagrams/backend_classes.puml)

## Related Test Cases
- [TC-04: Hybrid Ranking Tests](../test-cases/TC04-hybrid-ranking.md)
