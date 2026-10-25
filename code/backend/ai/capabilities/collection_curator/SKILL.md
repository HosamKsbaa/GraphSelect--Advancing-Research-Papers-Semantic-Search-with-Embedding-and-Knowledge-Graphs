---
name: collection-curator
description: Inspect PaperCollection coverage, abstract availability, and PRISMA 2020 screening flow counts.
---

# Skill: Collection Curator (`collection-curator`)

## When to Load
Load this skill when auditing collection statistics, missing-abstract coverage, or PRISMA screening counts.

## Protocol
1. Inspect `total_papers`, `available_abstracts`, and `missing_abstracts` via `get_collection(collection_id)`.
2. Preserve papers with missing abstracts in the collection record while excluding them from verbatim quote synthesis.
