import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from routers.search import router as search_router

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
    version='1.0.0',
)

app.include_router(search_router)

STATIC_DIR: Path = Path(__file__).parent / 'static'


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
async def serve_ui() -> HTMLResponse:
    """Serve the test UI."""
    return HTMLResponse((STATIC_DIR / 'index.html').read_text(encoding='utf-8'))


@app.get('/api/health')
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {'status': 'healthy', 'service': 'ALRS GraphSelect API'}

