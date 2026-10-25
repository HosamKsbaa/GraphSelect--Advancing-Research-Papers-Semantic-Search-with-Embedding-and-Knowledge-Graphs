# newcode: instructions for coding agents

Active code for the ALRS research agent (master's thesis). Python 3.13, FastAPI, Pydantic v2.
The plan this code follows: `../brain/decisions/single-research-agent.md` (parent workspace).

## Layout (`code/`)
- `backend/`
  - `api/`      HTTP routes and request/response models only
  - `engines/`  deterministic building blocks: `openalex`, `embeddings`, `alrs`, `jev`, plus `papers.py` and `errors.py`
  - `ai/`       the single research agent: `agent.py`, `capabilities/<name>/{SKILL.md,tools.py}`, `mcp_server.py`
  - `tests/`    backend tests mirroring the layout; external providers are always replaced with fixtures
  - `main.py`   creates clients once at startup and passes them in; `config.py` holds settings
- `frontend/`
  - `index.html` single-page UI served by the backend at `/`
  - `tests/`     automated frontend tests (`node --test`)

> **In progress (2026-10-25):** `engines/openalex` and `engines/embeddings` are done; `engines/alrs` and
> `engines/jev` are next. `ai/` does not exist yet. Inside `api/`, the v2.4.0 `api/services/` still backs
> `/api/search` until engine step 6 replaces it with `engines/alrs`; do not extend `api/services/`.

## Dependency rules (to be enforced by `backend/tests/engines/test_engine_boundaries.py`)
- `api → ai → engines`; `api → engines` is allowed. `engines` never import `ai` or `api`.
- Code outside `engines/` imports only `engines.<name>`, never internal modules such as `engines.openalex.budget`.

## Commands
```bash
cd newcode && PYTHONPATH=code/backend code/backend/.venv/bin/python -m pytest code/backend/tests -q   # run from newcode/ so code/backend/.env is not loaded
cd newcode/code/backend && .venv/bin/python -m mypy --strict engines
cd newcode && node --test code/frontend/tests/*.test.mjs
```
Set up once: `cd newcode/code/backend && uv venv .venv --python 3.13 && uv pip install --python .venv/bin/python -r requirements.txt mypy`

## Rules
- Apply `.agents/skills/alrs-readable-code/SKILL.md` to every code change.
- Typed Pydantic models at every boundary; no untyped dicts passed through the app.
- Failures stay failures: never return empty success or invented papers, scores, DOIs or citations.
- Missing values stay visible (no abstract → no similarity score).
- No live API calls in tests.
- Porting from the archive: stay as close to the source as possible; name the source file and
  commit 865cd08 in the module docstring and the commit message.
- Researcher-facing text uses plain everyday language.
- Embeddings: `.agents/rules/gemini_embeddings.md`. OpenAlex: `.agents/rules/openalex_guide.md`.

## Do not
- Edit the archive (`../archive/`); it is a read-only reference.
- Attribute the thesis LitSearch results to new code unless they were re-run with it.
