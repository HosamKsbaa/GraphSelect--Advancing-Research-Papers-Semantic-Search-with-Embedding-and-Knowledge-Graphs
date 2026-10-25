---
name: verify-citations
description: Audit a synthesized literature review to strip invented or unsupported DOIs and confirm exact quote provenance.
---

# Skill: Verify Citations (`verify-citations`)

## When to Load
Load this skill immediately before returning a final review (`verify_citations` gate).

## Protocol
1. Call `verify_citations(collection_id, review_output)` to check every bracketed `[10.xxxx/...]` DOI against the saved `PaperCollection`.
2. Any DOI not present in `collection.entries` is recorded in `unsupported_dois` and removed from `cleaned_markdown`.
3. Confirm `verified=True` when all cited DOIs belong to the collection and at least one verified finding is present.
