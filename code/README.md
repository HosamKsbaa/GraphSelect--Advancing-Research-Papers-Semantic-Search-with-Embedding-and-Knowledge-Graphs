# ALRS v2 — Automated Literature Review System

An agent-based automated literature review assistant. A researcher provides a seed paper (DOI or title) and up to 6 research questions. The system crawls adjacent papers via citation graphs, filters by semantic similarity, ranks using a hybrid score, and produces structured literature reviews.

## Project Structure

```
newcode/code/
├── backend/       # FastAPI + Neo4j + MySQL (Python)
├── frontend/      # Flutter UI (Dart)
├── legacy/        # v2.x codebase (archived — do not modify)
├── docker-compose.yml  # Orchestrates all services
└── README.md      # This file
```

## Quick Start

```bash
# 1. Copy environment template
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# 2. Start all services
docker-compose up -d

# 3. Access
# Backend API:  http://localhost:8000
# Neo4j Browser: http://localhost:7474
# Flutter Web:   http://localhost:8080 (when built)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11+ |
| Graph DB | Neo4j 5.x + GDS Plugin |
| Relational DB | MySQL 8.0 |
| Embeddings | Gemini API (gemini-embedding-001) |
| Agent Framework | Google ADK |
| Frontend | Flutter (Web + Desktop) |
| Deployment | Docker Compose |

## Development

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md) for component-specific setup.
