# ALRS GraphSelect API (v2.3.1)

Python/FastAPI implementation of the **GraphSelect algorithm** — a semantic paper search system for the Automated Literature Review System (ALRS).

Ported from the original Flutter/Dart implementation.

## Algorithm

The GraphSelect algorithm discovers relevant academic papers by:

1. **Embedding research questions** via Gemini API (`text-embedding-004`)
2. **Traversing citation graphs** via BFS using the OpenAlex API
3. **Filtering by cosine similarity** (default threshold ≥ 0.3)
4. **Ranking via PageRank** (20 iterations, damping = 0.85)
5. **Combined scoring**: 70% similarity + 30% PageRank

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
set GEMINI_API_KEY=your_api_key_here
set OPENALEX_EMAIL=your_email@example.com  # Optional, for polite pool

# Run the server
uvicorn main:app --reload

# Open API docs
# http://localhost:8000/docs
```

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

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
code/
├── main.py              # FastAPI entry point
├── config.py            # Settings via pydantic-settings
├── models/              # Pydantic data models
├── services/            # Business logic & API wrappers
├── routers/             # FastAPI route handlers
└── tests/               # pytest test suite
```
