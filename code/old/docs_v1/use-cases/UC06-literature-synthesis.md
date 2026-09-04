# UC-06: Literature Synthesis

## Overview
- **Actor**: Researcher
- **Priority**: P2
- **Status**: 🔴 Not Started
- **Phase**: Phase 6

## Description
AI agents (powered by Gemini) analyze the ranked and grouped papers to produce a structured literature review. For each research question group, the system generates a narrative synthesis that summarizes key findings, identifies themes, highlights agreements and contradictions, and includes proper citations. The generated review undergoes citation validation to ensure all referenced papers exist in the citation graph.

## Preconditions
- Hybrid ranking is complete with GroupedResults available (UC-04 complete)
- At least one research question has papers above the similarity threshold
- Gemini generative AI API is accessible
- Paper metadata (title, abstract, authors, year) is available in Neo4j

## Main Flow
1. Researcher triggers literature synthesis from the results view
2. System retrieves GroupedResults for all research questions
3. For each research question group:
   a. System prepares a context prompt with the top-N ranked papers (title, abstract, year, DOI)
   b. System sends the prompt to Gemini with structured output instructions
   c. Gemini generates a narrative synthesis paragraph (300–800 words)
   d. System extracts inline citations from the generated text
   e. System validates that each citation DOI exists in the session's Neo4j graph
4. System assembles the full literature review document with:
   - Introduction / overview
   - Per-question synthesis sections
   - Cross-question themes (if applicable)
   - References list with DOIs
5. System presents the review to the researcher for editing
6. Researcher may regenerate individual sections or accept the review

## Alternative Flows
- **AF-01: Gemini API failure** — System retries 3 times with backoff. If persistent, partial review is returned with sections marked as `[Generation Failed]`.
- **AF-02: Invalid citation detected** — Generated text references a paper not in the graph. System removes or flags the citation and adds a warning annotation.
- **AF-03: Too many papers in a group** — Group has >50 papers. System truncates to top-30 by hybrid score and notes the truncation in the review.
- **AF-04: Single paper per question** — Only one paper available. System generates a brief summary instead of a comparative synthesis.

## Postconditions
- Structured literature review document is generated and stored
- All citations in the review are validated against the Neo4j graph
- Review is exportable in Markdown format
- Generation metadata (model, token count, timestamp) is logged

## Related Diagrams
- [Backend Classes Diagram](../diagrams/backend_classes.puml)
- [API Flow Diagram](../diagrams/api_flow.puml)

## Related Test Cases
- [TC-06: Literature Synthesis Tests](../test-cases/TC06-literature-synthesis.md)
