"""FastAPI application entry point for ALRS v2 backend."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.neo4j_service import Neo4jService
from db.neo4j_schema import initialize_schema
from db.mysql_service import MySQLService

logger = logging.getLogger(__name__)

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

    # Neo4j
    neo4j_service = Neo4jService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await neo4j_service.connect()
    await initialize_schema(neo4j_service, settings.embedding_dimensions)
    app.state.neo4j_service = neo4j_service

    # MySQL
    mysql_service = MySQLService(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
    )
    await mysql_service.connect()
    await mysql_service.initialize_schema()
    app.state.mysql_service = mysql_service

    logger.info("ALRS v2 backend started successfully")

    yield

    # --- Shutdown ---
    logger.info("Shutting down ALRS v2 backend...")
    if hasattr(app.state, "neo4j_service") and app.state.neo4j_service is not None:
        await app.state.neo4j_service.close()
    if hasattr(app.state, "mysql_service") and app.state.mysql_service is not None:
        await app.state.mysql_service.close()
    logger.info("ALRS v2 backend shut down")


# --- Create FastAPI app ---
app = FastAPI(
    title="ALRS v2 — Automated Literature Review System",
    description="Agent-based automated literature review assistant",
    version=_read_version(),
    lifespan=lifespan,
)

# --- CORS middleware ---
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
    """Health check endpoint verifying Neo4j + MySQL connectivity."""
    neo4j_ok = False
    mysql_ok = False
    if hasattr(request.app.state, "neo4j_service") and request.app.state.neo4j_service is not None:
        neo4j_ok = await request.app.state.neo4j_service.health_check()
    if hasattr(request.app.state, "mysql_service") and request.app.state.mysql_service is not None:
        mysql_ok = await request.app.state.mysql_service.health_check()

    status = "healthy" if (neo4j_ok and mysql_ok) else "degraded"
    return {
        "status": status,
        "neo4j": "connected" if neo4j_ok else "disconnected",
        "mysql": "connected" if mysql_ok else "disconnected",
    }


@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return the current application version."""
    return {"version": _read_version()}


# --- Register routers ---
from routers.search import router as search_router
from routers.sessions import router as sessions_router
from routers.papers import router as papers_router
from routers.logs import router as logs_router
from routers.debug import router as debug_router
from routers.settings import router as settings_router

app.include_router(search_router)
app.include_router(sessions_router)
app.include_router(papers_router)
app.include_router(logs_router, prefix="/api")
app.include_router(debug_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


# --- Configure logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
