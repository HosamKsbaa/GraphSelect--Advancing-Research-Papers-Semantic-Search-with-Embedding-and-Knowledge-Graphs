# Copilot Instructions for ALRS GraphSelect API

This repository contains the ALRS GraphSelect API, a high-performance academic literature semantic search API using FastAPI, OpenAlex, and Google Gemini embeddings.

For full architectural blueprints, algorithm schemas, and detailed coding conventions, see the **[AI Developer Handbook & Architecture Guide](../AI_README.md)**.

## 🚀 Quick Reference for AI Assistants

### 1. General Rules
- Always use type hints (`PEP 484`) for all parameters and return values.
- Never import and instantiate the `Settings` class directly in routers or services. Always use the cached singleton provider:
  ```python
  from config import get_settings
  settings = get_settings()
  ```
- Use Google-style docstrings and explain the high-level intent of files in module docstrings.
- Always use the `logging` module; do not write `print` statements.

### 2. Algorithmic Constants & Logic
- **Similarity Threshold**: Cosine similarity $\ge$ `similarity_threshold` (default `0.3`) using `gemini-embedding-001`.
- **PageRank**: Standard iterative power method. 20 iterations, damping factor of `0.85` on the BFS subgraph nodes.
- **Combined Score**: `0.7 * Similarity + 0.3 * PageRank`.

### 3. External API Client
- Do not create unmanaged HTTP connections. Always close or aclose client sessions.
- OpenAlex abstract reconstruction uses `OpenAlexService.reconstruct_abstract(inverted_index)`.

### 4. Versioning
- Versioning is strictly read from `code/VERSION`.
- To bump versions, execute `python bump_version.py <new_version>` from the root of this repository.

### 5. Testing
- Place test files under `code/tests/`.
- Mock external dependencies (`GeminiService.get_embedding` and `OpenAlexService`) using fixtures in `code/tests/conftest.py`.
- Run tests via `pytest tests/ -v`.
