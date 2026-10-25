---
name: write-literature-review
description: Synthesize a structured literature review grounded strictly in exact sentence spans from a saved PaperCollection.
---

# Skill: Write Literature Review (`write-literature-review`)

## When to Load
Load this skill after discovery completes, when synthesizing findings from a saved `PaperCollection` (`synthesize_review`).

## Protocol
1. Call `get_collection(collection_id)` to retrieve every saved paper and its `available_sources` sentence spans (`entry_id`, `start_char`, `end_char`, `quote`, `sha256`).
2. Construct `AnalysisFinding` items for each research question using only verbatim `PaperSourceReference` spans from `available_sources`.
3. Call `write_review(collection_id, findings)` to validate every quote span via `validate_sources` and render a Markdown literature review with inline `[DOI]` tags and APA/BibTeX references.
