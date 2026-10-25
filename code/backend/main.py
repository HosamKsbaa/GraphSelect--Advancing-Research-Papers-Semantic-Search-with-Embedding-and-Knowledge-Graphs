import sys
import logging
import webbrowser
import threading
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from ai import AgentToolRuntime, create_mcp_router
from api.routers.search import router as search_router
from config import get_settings
from engines.alrs import AlrsEngine
from engines.collections import InMemoryCollectionStore
from engines.embeddings import GeminiEmbeddingClient
from engines.openalex import OpenAlexClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

APP_VERSION = (Path(__file__).parent / 'VERSION').read_text(encoding='utf-8').strip()

app: FastAPI = FastAPI(
    title='ALRS GraphSelect API',
    description=(
        'Automated Literature Review System — GraphSelect Algorithm.\n\n'
        'Implements semantic paper search using citation graph traversal,\n'
        'Gemini embeddings, cosine similarity filtering, and PageRank ranking.'
    ),
    version=APP_VERSION,
)

app.include_router(search_router)


def get_agent_runtime() -> AgentToolRuntime:
    runtime = getattr(app.state, "agent_runtime", None)
    if isinstance(runtime, AgentToolRuntime):
        return runtime
    openalex = OpenAlexClient()
    embeddings = GeminiEmbeddingClient(client=None)
    default_runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
        collection_store=InMemoryCollectionStore(),
    )
    app.state.agent_runtime = default_runtime
    return default_runtime


app.include_router(create_mcp_router(get_agent_runtime))

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # PyInstaller bundles the frontend next to the executable's code (see build_exe.py).
    FRONTEND_DIR: Path = Path(sys._MEIPASS) / 'frontend'
else:
    # Source and Docker layouts both keep frontend/ beside backend/.
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'frontend'


def open_browser_tab(url: str, delay_seconds: float = 1.0) -> None:
    """Wait for server to start, then open the browser to the application URL."""
    time.sleep(delay_seconds)
    webbrowser.open(url)


@app.on_event("startup")
def on_startup() -> None:
    """FastAPI startup event handler."""
    settings = get_settings()
    if settings.open_browser:
        url = "http://127.0.0.1:8000"
        logging.info(f"Opening default browser at {url}...")
        threading.Thread(target=open_browser_tab, args=(url,), daemon=True).start()


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
async def serve_ui() -> HTMLResponse:
    """Serve the frontend page."""
    return HTMLResponse((FRONTEND_DIR / 'index.html').read_text(encoding='utf-8'))


@app.get('/api/health')
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {'status': 'healthy', 'service': 'ALRS GraphSelect API'}


@app.get('/api/version')
async def version_info() -> dict[str, str]:
    """Return the current application version."""
    return {'version': APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
