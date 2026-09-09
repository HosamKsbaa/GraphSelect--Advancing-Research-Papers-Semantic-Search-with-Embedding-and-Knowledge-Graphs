"""FastAPI application entry point for ALRS v2 backend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from core.db.neo4j_service import Neo4jService
from core.db.neo4j_schema import initialize_schema
from core.logging.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)

MAX_CONNECT_RETRIES = 10
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

# --- Application state (populated during lifespan) ---

def _read_version() -> str:
    """Read version from VERSION file."""
    version_file = Path(__file__).parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""

    settings = get_settings()

    # --- Startup ---
    logger.info("Starting ALRS v2 backend...")

    # Neo4j (with retry)
    neo4j_service = Neo4jService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            await neo4j_service.connect()
            logger.info("Neo4j connected on attempt %d", attempt)
            break
        except Exception as exc:
            if attempt == MAX_CONNECT_RETRIES:
                logger.error("Neo4j connection failed after %d attempts, giving up", MAX_CONNECT_RETRIES)
                raise
            logger.warning("Neo4j not ready (attempt %d/%d): %s — retrying in %.1fs",
                           attempt, MAX_CONNECT_RETRIES, exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    await initialize_schema(neo4j_service, settings.embedding_dimensions)
    app.state.neo4j_service = neo4j_service

    # SQLite Telemetry Service
    app.state.telemetry_service = TelemetryService(settings.sqlite_telemetry_path)

    from core.logging.progress_service import ProgressService
    app.state.progress_service = ProgressService()

    from core.llm.service import LLMService
    try:
        app.state.llm_service = LLMService(api_key=settings.gemini_api_key)
        logger.info("LLMService initialized successfully in app.state")
    except Exception as exc:
        logger.warning("LLMService initialization deferred or warning: %s", exc)
        app.state.llm_service = None

    logger.info("ALRS v2 backend started successfully")

    yield

    # --- Shutdown ---
    logger.info("Shutting down ALRS v2 backend...")
    if hasattr(app.state, "neo4j_service") and app.state.neo4j_service is not None:
        await app.state.neo4j_service.close()
    logger.info("ALRS v2 backend shut down")


# --- Create FastAPI app ---
app = FastAPI(
    title="ALRS v2 — Automated Literature Review System",
    description="Agent-based automated literature review assistant",
    version=_read_version(),
    lifespan=lifespan,
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health and version endpoints ---
@app.get("/api/health")
async def health_check(request: Request) -> dict[str, object]:
    """Health check endpoint verifying pure Neo4j connectivity."""
    neo4j_ok = False
    if hasattr(request.app.state, "neo4j_service") and request.app.state.neo4j_service is not None:
        neo4j_ok = await request.app.state.neo4j_service.health_check()

    status_val = "healthy" if neo4j_ok else "degraded"
    return {
        "status": status_val,
        "neo4j": "connected" if neo4j_ok else "disconnected",
    }


@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return the current application version."""
    return {"version": _read_version()}


# --- Register routers (feature-based) ---
from features.search.router import router as search_router
from features.sessions.router import router as sessions_router
from features.retrieval.router import router as papers_router
from features.logs.router import router as logs_router
from features.debug.router import router as debug_router
from features.settings.router import router as settings_router
from features.research.router import router as research_router
from features.analysis.router import router as analysis_router
from features.planning.router import router as planning_router
from features.writing.router import router as writing_router
from features.export.router import router as export_router
from features.chat.router import router as chat_router
from features.agents.router import router as agents_router
from projects.router import router as projects_router
from features.workflow.router import router as workflow_router
from features.ingestion.router import router as ingestion_router

app.include_router(search_router)
app.include_router(sessions_router)
app.include_router(papers_router)
app.include_router(logs_router, prefix="/api")
app.include_router(debug_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(research_router)
app.include_router(analysis_router)
app.include_router(planning_router)
app.include_router(writing_router)
app.include_router(export_router)
app.include_router(chat_router)
app.include_router(projects_router)
app.include_router(workflow_router, prefix="/api")
app.include_router(ingestion_router)


# --- Configure logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
