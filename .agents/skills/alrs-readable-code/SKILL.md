---
name: alrs-readable-code
description: Write, refactor, and review ALRS Python and Angular code using readable names, straightforward control flow, and simple feature-based organization. Use when implementing or reviewing code in the ALRS project.
---

# Write readable ALRS code

Write for a developer who understands basic Python or TypeScript but is new
to this project. They should be able to follow the feature without opening
many unrelated files.

Prefer clear code over clever code. Simplicity must preserve validation,
persistence, error handling, and correct research behavior.

## 1. Keep the feature structure simple

Use the existing folders:

- `api/`: HTTP requests, access checks, streaming, and responses.
- `ai/functions/`: specialist agents, graphs, prompts, and tools.
- `ai/core/`: shared workflow execution, checkpoints, and events.
- `ai/library/`, `ai/documents/`, `ai/evidence/`, `ai/artifacts/`: shared research services, added only when implemented.
- `alrs_tool/`: academic providers, discovery, citation traversal, and ranking.
- `langfuse_integration/`: tracing.
- `frontend/src/app/features/`: Angular features.

Create a file when it has a real responsibility. Do not create empty
directories or a standard pile of files for every feature.

DO:

```text
search/
  router.py
  models.py
  service.py
  tests/
```

Add `repository.py` when that feature needs database operations.

DO NOT create this without a demonstrated need:

```text
search/
  factories/
  managers/
  interfaces/
  abstract_services/
  service_implementations/
  generic_handlers/
  helpers/
  utils/
```

Keep existing modules when their responsibilities are clear. Do not
reorganize unrelated code just to match an example in this skill.

## 2. Use names that explain the work

Name functions with a specific action and object:

- `fetch_paper()`
- `save_screening_decision()`
- `calculate_prisma_counts()`
- `cancel_run()`

Avoid vague names such as `process()`, `execute()`, `handle_data()`, and `manager`
when a more specific name is available.

DO NOT:

```python
def calc(a: int, b: int) -> int:
    return max(0, a - b)
```

DO:

```python
def calculate_remaining_papers(
    paper_limit: int,
    saved_paper_count: int,
) -> int:
    return max(0, paper_limit - saved_paper_count)
```

Use ordinary domain words. Introduce an abbreviation only when it is
already familiar in the project, such as DOI or API.

## 3. Make decisions easy to read

Use early returns for invalid or unsupported conditions. Use named
intermediate values when they explain a calculation.

Simple comprehensions are fine. Replace nested expressions when they
hide the decisions being made.

DO NOT:

```python
status = "unknown" if score is None else "high" if score >= threshold else "low"
```

DO:

```python
if score is None:
    status = "unknown"
elif score >= threshold:
    status = "high"
else:
    status = "low"
```

Keep functions focused on one responsibility.

Follow the project's function-size rules: agent tools, API handlers,
and graph query runners must stay under 25 lines. Split at meaningful
boundaries such as validation, calculation, persistence, and response
formatting.

Do not create dozens of one-line forwarding functions merely to reduce
line counts.

## 4. Use clear types at boundaries

Use Pydantic models for Python requests, results, and domain records.
Use explicit TypeScript interfaces for frontend contracts.

DO NOT pass an unexplained dictionary through the whole application:

```python
async def start_search(data: dict[str, object]):
    ...
```

DO define what the request contains:

```python
from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    project_id: UUID
    seed_doi: str
    max_papers: int = Field(default=25, ge=1, le=100)
```

Validate external data when it enters the application. Internal business
logic should receive a validated model rather than repeatedly guessing
whether a value is a dictionary, string, or model.

Use the state representation required by the installed LangGraph API.
Typed partial state-update dictionaries are acceptable at that framework
boundary; they do not justify untyped business logic.

The examples in this skill are illustrative. Reuse existing domain
types instead of creating duplicate models.

## 5. Show dependencies explicitly

Create database, provider, and model clients during application startup.
Pass them into the services that need them.

DO NOT hide a client in a module-level global:

```python
client = OpenAlexClient()


async def fetch_paper(doi: str) -> Paper:
    return await client.fetch_paper(doi)
```

DO make the dependency visible:

```python
async def fetch_paper(
    doi: str,
    client: OpenAlexClient,
) -> Paper:
    return await client.fetch_paper(doi)
```

Choose a function for a simple operation. Use a class when it owns a
connection, lifecycle, or a coherent group of operations.

Do not introduce a factory, base class, or plugin registry for one
implementation.

Preserve dependency direction:

- API routes call application services.
- Graph nodes call research services and tools.
- Provider and storage adapters perform external I/O.
- AI code must not import an API router to reuse its implementation.

When both an API route and a graph need an operation, put that operation
in the appropriate shared service.

## 6. Make success and failure truthful

Return success only after the required operation succeeds.

DO NOT:

```python
try:
    await repository.save(paper)
except Exception:
    pass

return SaveResult(saved=True)
```

DO:

```python
saved_paper = await repository.save(paper)

return SaveResult(
    saved=True,
    paper_id=saved_paper.id,
)
```

Let unexpected failures reach the application's error boundary.
Catch a specific exception only when this layer can retry, recover, or
translate it into a meaningful result.

Never turn a provider or database failure into an empty successful result.

Keep these outcomes distinct:

- No papers matched.
- Search failed.
- Search returned partial results.
- The capability is not implemented.

Do not fabricate papers, citations, connection checks, approval scores,
or progress percentages.

## 7. Keep LangGraph steps explicit

Name nodes after the step they perform:

```text
validate_request
request_approval
discover_papers
save_results
```

Keep provider calls and database queries in their adapters rather than
embedding them inside long graph nodes.

A node should return only its intended state changes.

For an append-reduced artifacts field, DO NOT return the accumulated list:

```python
return {
    "artifacts": state["artifacts"] + [new_artifact],
}
```

DO return only the addition:

```python
return {
    "artifacts": [new_artifact],
}
```

Check the field's reducer before changing its update behavior. Fields
without append reducers may require replacement values.

Do not simplify away cancellation, approval, or checkpoint behavior.
Their state transitions must remain visible and testable.

## 8. Keep frontend data honest

Use nullable types for values that may be unavailable.

DO NOT invent a score to make a component render:

```typescript
const similarity = paper.similarityScore ?? 0.8;
```

DO display the missing value clearly:

```typescript
const similarityLabel =
  paper.similarityScore === null
    ? 'Not calculated'
    : paper.similarityScore.toFixed(2);
```

This example assumes `similarityScore` is typed as `number | null`.

Keep templates focused on display. Put shared HTTP behavior in API
services and reusable calculations in named functions.

Do not display a successful save before the server confirms it.

## 9. Explain reasons, not obvious syntax

DO NOT:

```python
# Increase the counter by one.
saved_count += 1
```

DO:

```python
# Count only committed records so progress survives a restart.
saved_count += 1
```

Use comments for assumptions, domain rules, and non-obvious tradeoffs.
Use short docstrings for public operations where inputs, outputs, or
side effects need explanation.

Do not narrate every line or add decorative comment banners.

## 10. Test observable behavior

Use test names that explain the requirement:

- `test_missing_evidence_prevents_approval`
- `test_duplicate_doi_is_saved_once`
- `test_cancelled_run_never_becomes_completed`
- `test_restart_preserves_project_papers`

Test calculations with concrete inputs and expected outputs.
Test storage and API boundaries with the real internal implementation.
Replace external providers with controlled fixtures in automated tests.

Do not write tests that only confirm the code calls its own helper.
Do not weaken assertions to make a failing implementation pass.

For a readability-only change, run the relevant existing checks.
Add tests when behavior changes or a real gap in coverage is found.

## Before finishing

Check that:

- Names explain what the code does.
- The main flow reads in a clear order.
- Files have real responsibilities.
- Dependencies are visible.
- Failures cannot appear as success.
- State updates match their reducers.
- Tests cover the behavior changed.
- Unrelated code and existing user changes remain untouched.

Explain what changed, why it helps, and how it was verified in plain
language. Report remaining failures honestly.
