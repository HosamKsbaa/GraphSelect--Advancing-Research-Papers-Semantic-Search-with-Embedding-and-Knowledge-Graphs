# ALRS GraphSelect API

![Version](https://img.shields.io/badge/version-2.4.2--beta-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-BSD--3--Clause-blue?style=flat-square)

Python/FastAPI implementation of the **GraphSelect algorithm** — a semantic paper search system for the Automated Literature Review System (ALRS).

Ported from the original Flutter/Dart implementation.

---

## Quick Start (Docker)

The fastest way to run GraphSelect is with Docker. No Python environment required.

### One-liner

```bash
docker run -e GEMINI_API_KEY=your_key -p 8000:8000 ghcr.io/hosamksbaa/graphselect:latest
```

The API will be available at **http://localhost:8000/docs**.

### Bootstrap Scripts

Platform-specific scripts that handle everything automatically:

```bash
# Linux / macOS
./run_graphselect.sh

# Windows
run_graphselect.bat
```

### Docker Compose

For a more configurable setup, use Docker Compose:

```bash
docker compose up
```

Environment variables can be configured in a `.env` file or directly in `docker-compose.yml`:

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | **Yes** | Your Google Gemini API key |
| `OPENALEX_EMAIL` | No | Email for OpenAlex polite pool (higher rate limits) |

---

## Algorithm

The GraphSelect algorithm discovers relevant academic papers by:

1. **Embedding research questions** via Gemini API (`gemini-embedding-001`)
2. **Traversing citation graphs** via BFS using the OpenAlex API
3. **Filtering by cosine similarity** (default threshold ≥ 0.3)
4. **Ranking via PageRank** (20 iterations, damping = 0.85)
5. **Combined scoring**: 70% similarity + 30% PageRank

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/search` | Run GraphSelect algorithm |
| `GET` | `/api/health` | Health check |

### Example Request

```json
POST /api/search
{
  "seed_doi": "10.1038/s41586-020-2649-2",
  "research_questions": [
    "How does array programming impact scientific computing?"
  ],
  "similarity_threshold": 0.3,
  "max_depth": 3,
  "max_neighbors_per_level": 25
}
```

## 🌿 Branching & Release Strategy

We follow a structured branching and release strategy to ensure code quality and seamless deployments:

* **`main` (Production)**: Holds the stable, production-ready code. Stable production releases (e.g., `v2.4.0`) are tagged and published solely from this branch. Never commit directly to `main`.
* **`dev` (Development / Beta)**: The primary integration branch for active refactoring and additions. All beta test releases (e.g., `v2.4.0-beta.1`) are tagged and published solely from this branch.
* **Isolated Branches (`feature/*`, `bugfix/*`)**: All isolated tasks and experimental feature edits must be hosted on separate branches, and then merged into `dev` via pull requests.

---

## Development Setup

To run from source without Docker:

```bash
# Clone and enter the project
cd code/

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY=your_api_key_here
export OPENALEX_EMAIL=your_email@example.com  # Optional, for polite pool

# On Windows use 'set' instead of 'export':
# set GEMINI_API_KEY=your_api_key_here
# set OPENALEX_EMAIL=your_email@example.com

# Run the server
uvicorn main:app --reload

# Open API docs
# http://localhost:8000/docs
```

---

## Testing

```bash
pytest tests/ -v
```

---

## Project Structure

```
code/
├── main.py                # FastAPI entry point
├── config.py              # Settings via pydantic-settings
├── Dockerfile             # Container image definition
├── docker-compose.yml     # Multi-service orchestration
├── run_graphselect.sh     # Bootstrap script (Linux/macOS)
├── run_graphselect.bat    # Bootstrap script (Windows)
├── requirements.txt       # Python dependencies
├── models/                # Pydantic data models
├── services/              # Business logic & API wrappers
├── routers/               # FastAPI route handlers
└── tests/                 # pytest test suite
```
