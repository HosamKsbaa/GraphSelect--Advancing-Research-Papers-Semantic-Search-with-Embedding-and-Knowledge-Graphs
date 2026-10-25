---
name: search-literature
description: Find high-signal seed papers in OpenAlex and expand citation neighborhoods with E-GraphSelect.
---

# Skill: Search Literature (`search-literature`)

## When to Load
Load this skill during seed selection and citation-graph discovery (`select_seed` and `discover`).

## Protocol
1. Call `search_papers(query, limit=5)` to retrieve candidate seed works with DOIs from OpenAlex.
2. Prefer a seed work with a non-empty abstract (`has_abstract=True`) and strong topical overlap.
3. Call `discover_literature(seed_doi, research_questions, max_depth, similarity_threshold)` to run E-GraphSelect (cosine similarity + density-gated PageRank) and persist an immutable `PaperCollection`.
4. Never fabricate a DOI or paper title; only use DOIs returned by `search_papers` or `discover_literature`.
