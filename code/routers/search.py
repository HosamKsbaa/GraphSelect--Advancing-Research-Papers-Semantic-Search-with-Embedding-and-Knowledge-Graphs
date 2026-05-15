"""Search router — REST + SSE streaming endpoints for GraphSelect."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from models.progress import GraphSearchProgress
from models.ranked_paper import RankedPaper
from services.graph_search_service import GraphSearchService
from config import get_settings

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix='/api', tags=['search'])

# --------------------------------------------------------------------------- #
#  Request / Response schemas
# --------------------------------------------------------------------------- #


class SearchRequest(BaseModel):
    """Request schema for the GraphSelect search endpoint."""

    seed_doi: str = Field(..., description='DOI of the seed paper to start from')
    research_questions: list[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description='Research questions (1-6) to guide the search',
    )
    similarity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description='Minimum cosine similarity to keep a paper',
    )
    max_depth: int = Field(
        default=3,
        ge=1,
        le=10,
        description='Maximum BFS depth for citation traversal',
    )
    max_neighbors_per_level: int = Field(
        default=25,
        ge=1,
        le=100,
        description='Maximum papers to examine per BFS level',
    )
    gemini_api_key: str | None = Field(
        default=None,
        description='Optional Gemini API key to override environment settings',
    )
    openalex_email: str | None = Field(
        default=None,
        description='Optional OpenAlex email to override environment settings',
    )


class SearchResponse(BaseModel):
    """Response schema for the GraphSelect search endpoint."""

    results: list[RankedPaper]
    total_results: int
    total_papers_processed: int
    total_api_calls: int


# --------------------------------------------------------------------------- #
#  SSE helpers
# --------------------------------------------------------------------------- #

_SENTINEL = object()
"""Sentinel pushed onto the queue to signal end-of-stream."""


def _sse_frame(event_type: str, data: str) -> str:
    """Format a single Server-Sent Events frame.

    Returns a string in the standard SSE wire format::

        event: <event_type>
        data: <json_string>
        <blank line>
    """
    return f"event: {event_type}\ndata: {data}\n\n"


def _build_service(request: SearchRequest) -> tuple[GraphSearchService, 'asyncio.Queue[object]']:
    """Create a ``GraphSearchService`` wired to an ``asyncio.Queue``.

    Both the progress callback and the paper-event callback push
    their payloads onto the same queue so the SSE generator has a
    single consumption point.  The callbacks are **synchronous**
    (``put_nowait``) because they are invoked from within the
    service's ``await``-ed coroutines on the *same* event loop.

    Returns:
        A ``(service, queue)`` tuple.
    """
    settings = get_settings()

    api_key: str | None = request.gemini_api_key or settings.gemini_api_key
    email: str | None = request.openalex_email or settings.openalex_email

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail='GEMINI_API_KEY is not configured. '
                   'Please provide it in the UI fields or environment variables.',
        )

    queue: asyncio.Queue[object] = asyncio.Queue()

    def _on_progress(progress: GraphSearchProgress) -> None:
        """Bridge sync progress callback → async queue."""
        queue.put_nowait(('progress', progress.model_dump(mode='json')))

    def _on_paper_event(event: dict[str, object]) -> None:
        """Bridge sync paper-event callback → async queue."""
        status = event.get('status', 'unknown')
        queue.put_nowait((f'paper_{status}', event))

    service = GraphSearchService(
        research_questions=request.research_questions,
        seed_doi=request.seed_doi,
        api_key=api_key,
        similarity_threshold=request.similarity_threshold,
        max_depth=request.max_depth,
        max_neighbors_per_level=request.max_neighbors_per_level,
        on_progress=_on_progress,
        on_paper_event=_on_paper_event,
        openalex_email=email,
        embedding_model=settings.embedding_model,
        pagerank_iterations=settings.pagerank_iterations,
        pagerank_damping=settings.pagerank_damping,
        similarity_weight=settings.similarity_weight,
        pagerank_weight=settings.pagerank_weight,
        rate_limit_delay_ms=settings.rate_limit_delay_ms,
    )

    return service, queue


async def _run_search_and_signal(
    service: GraphSearchService,
    queue: 'asyncio.Queue[object]',
) -> None:
    """Execute the search in the background and push the final results.

    When the search completes (or fails) a sentinel is placed on the
    queue so the SSE generator knows to close the stream.
    """
    try:
        results: list[RankedPaper] = await service.search()

        response = SearchResponse(
            results=results,
            total_results=len(results),
            total_papers_processed=service.total_papers_processed,
            total_api_calls=service.total_api_calls,
        )
        queue.put_nowait(('results', response.model_dump(mode='json')))

    except Exception as exc:
        logger.error(f'Streaming search failed: {exc}', exc_info=True)
        queue.put_nowait(('error', {'detail': str(exc)}))

    finally:
        queue.put_nowait(_SENTINEL)


async def _sse_generator(queue: 'asyncio.Queue[object]') -> AsyncGenerator[str, None]:
    """Async generator that drains the queue and yields SSE frames.

    Stops as soon as the ``_SENTINEL`` value is received.
    """
    while True:
        item: object = await queue.get()
        if item is _SENTINEL:
            break
        event_type, payload = item  # type: ignore[misc]
        yield _sse_frame(event_type, json.dumps(payload, default=str))


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #


@router.post('/search', response_model=SearchResponse)
async def run_search(request: SearchRequest) -> SearchResponse:
    """Run the GraphSelect algorithm.

    Starts from a seed paper, traverses citation graphs,
    filters by semantic similarity, and ranks results
    using PageRank + similarity.
    """
    settings = get_settings()

    api_key = request.gemini_api_key or settings.gemini_api_key
    email = request.openalex_email or settings.openalex_email

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail='GEMINI_API_KEY is not configured. '
                   'Please provide it in the UI fields or environment variables.',
        )

    try:
        service = GraphSearchService(
            research_questions=request.research_questions,
            seed_doi=request.seed_doi,
            api_key=api_key,
            similarity_threshold=request.similarity_threshold,
            max_depth=request.max_depth,
            max_neighbors_per_level=request.max_neighbors_per_level,
            openalex_email=email,
            embedding_model=settings.embedding_model,
            pagerank_iterations=settings.pagerank_iterations,
            pagerank_damping=settings.pagerank_damping,
            similarity_weight=settings.similarity_weight,
            pagerank_weight=settings.pagerank_weight,
            rate_limit_delay_ms=settings.rate_limit_delay_ms,
        )

        results: list[RankedPaper] = await service.search()

        return SearchResponse(
            results=results,
            total_results=len(results),
            total_papers_processed=service.total_papers_processed,
            total_api_calls=service.total_api_calls,
        )

    except Exception as e:
        logger.error(f'Search failed: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/search/stream')
async def run_search_stream(request: SearchRequest) -> StreamingResponse:
    """Run GraphSelect with real-time SSE progress streaming.

    Accepts the same ``SearchRequest`` body as ``/api/search`` but
    returns a ``text/event-stream`` response.  Events are pushed as
    they occur:

    * ``progress`` — ``GraphSearchProgress`` JSON
    * ``paper_processing`` — a paper started being processed
    * ``paper_found`` — a relevant paper was added to the graph
    * ``paper_skipped`` — a paper was skipped (no abstract / below threshold)
    * ``results`` — final ``SearchResponse`` JSON
    * ``error`` — error detail if the search fails
    """
    service, queue = _build_service(request)

    # Kick off the search as a background task on the current event loop.
    # The task pushes events onto *queue*; the SSE generator drains them.
    asyncio.create_task(_run_search_and_signal(service, queue))

    return StreamingResponse(
        content=_sse_generator(queue),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
