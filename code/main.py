import sys
import logging
import webbrowser
import threading
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from routers.search import router as search_router
from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

app: FastAPI = FastAPI(
    title='ALRS GraphSelect API',
    description=(
        'Automated Literature Review System — GraphSelect Algorithm.\n\n'
        'Implements semantic paper search using citation graph traversal,\n'
        'Gemini embeddings, cosine similarity filtering, and PageRank ranking.'
    ),
    version='2.3.1',
)

app.include_router(search_router)

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

STATIC_DIR: Path = BASE_DIR / 'static'


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
    """Serve the test UI."""
    return HTMLResponse((STATIC_DIR / 'index.html').read_text(encoding='utf-8'))


@app.get('/api/health')
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {'status': 'healthy', 'service': 'ALRS GraphSelect API'}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
