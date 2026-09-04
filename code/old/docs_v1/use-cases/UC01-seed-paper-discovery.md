# UC-01: Seed Paper Discovery

## Overview
- **Actor**: Researcher
- **Priority**: P1
- **Status**: 🟢 Complete
- **Phase**: Phase 3

## Description
The researcher enters a paper title into the system. The system searches the OpenAlex academic database, returns a list of candidate papers matching the query, and the researcher selects one as the seed paper for subsequent citation crawling. The selected paper's DOI is stored and used as the root node for BFS traversal.

## Preconditions
- Backend API server is running and accessible
- OpenAlex API is reachable (no rate-limit blocks)
- Researcher has a paper title or partial title to search for

## Main Flow
1. Researcher enters a paper title in the search field
2. Frontend sends `POST /resolve-title` with the title string
3. Backend queries OpenAlex API for matching papers
4. Backend returns a ranked list of candidate papers (title, authors, year, DOI, citation count)
5. Researcher reviews candidates and selects one
6. System stores the selected paper's DOI as the seed for the search session
7. System confirms seed paper selection and enables BFS crawl initiation

## Alternative Flows
- **AF-01: No results found** — OpenAlex returns zero matches. System displays "No papers found" message and prompts the researcher to refine the query.
- **AF-02: OpenAlex API timeout** — System retries up to 3 times with exponential backoff, then returns an error with retry suggestion.
- **AF-03: Ambiguous results** — Multiple papers share similar titles. System displays all candidates with disambiguation details (year, journal, DOI).
- **AF-04: DOI already used** — The selected DOI was already used as a seed in a previous session. System warns but allows proceeding.

## Postconditions
- Selected paper DOI is stored and available for BFS citation crawl
- A new search session is initialized with the seed paper metadata
- The seed paper node exists in the system (ready for Neo4j insertion upon BFS start)

## Related Diagrams
- [API Flow Diagram](../diagrams/api_flow.puml)
- [Backend Classes Diagram](../diagrams/backend_classes.puml)

## Related Test Cases
- [TC-01: Seed Paper Discovery Tests](../test-cases/TC01-seed-paper-discovery.md)
