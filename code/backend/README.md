# ALRS v2 Backend

FastAPI backend for the Automated Literature Review System.

## Structure

```
backend/
├── main.py                # FastAPI app entry point
├── config.py              # Pydantic settings
├── pyproject.toml         # Project metadata + mypy strict config
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
├── VERSION                # Semantic version
├── Dockerfile             # Multi-stage Docker build
├── models/                # Pydantic data models
│   ├── paper.py           # Paper, Author, Venue, Keyword
│   ├── session.py         # Session, SearchRequest
│   ├── progress.py        # SSE event models
│   ├── ranked_paper.py    # RankedPaper, GroupedResults
│   ├── synthesis.py       # SynthesisResult (Phase 2)
│   └── chat.py            # ChatMessage, VisualComponent (Phase 3)
├── db/                    # Database services
│   ├── neo4j_service.py   # Neo4j async driver + Cypher queries
│   ├── neo4j_schema.py    # Constraints, indexes, vector index
│   └── mysql_service.py   # MySQL async pool + DDL
├── services/              # Business logic
│   ├── gemini_service.py  # Embedding API client
│   ├── openalex_service.py    # OpenAlex API client
│   ├── opencitations_service.py # OpenCitations API client
│   ├── graph_search_service.py  # Core GraphSelect algorithm
│   ├── rate_limiter.py    # Adaptive token-bucket
│   ├── log_service.py     # Structured logging + API recording
│   ├── synthesis_service.py   # AI review generation (Phase 2)
│   ├── export_service.py  # BibTeX + document export (Phase 3)
│   └── agent_service.py   # Google ADK agent setup (Phase 2)
├── routers/               # API route handlers
│   ├── search.py          # Search + streaming endpoints
│   ├── papers.py          # Paper lookup
│   ├── sessions.py        # Session CRUD
│   ├── settings.py        # Settings management
│   ├── logs.py            # Log viewer
│   ├── authors.py         # Author exploration (Phase 3)
│   ├── venues.py          # Venue exploration (Phase 3)
│   ├── exports.py         # BibTeX/review export (Phase 3)
│   └── chat.py            # Conversational agent (Phase 3)
├── agents/                # Google ADK agent definitions
│   ├── tools/             # ADK FunctionTools
│   │   ├── paper_search.py
│   │   ├── citation_graph.py
│   │   └── ranking.py
│   └── literature_agent.py  # Main LlmAgent
└── tests/                 # Test suite (all mocked)
    ├── conftest.py
    └── ...
```
