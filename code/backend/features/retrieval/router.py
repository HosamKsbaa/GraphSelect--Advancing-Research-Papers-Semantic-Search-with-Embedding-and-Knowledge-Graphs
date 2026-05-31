"""Paper lookup API endpoints for ALRS v2.

This router provides read-only endpoints for fetching paper metadata.
All query logic and record-to-model mapping lives in
:class:`~features.retrieval.service.RetrievalService`.

Design note — zero-RAM embedding policy:
    The RetrievalService deliberately omits the ``embedding`` property from
    all Cypher RETURN clauses.  Embeddings are stored and compared
    *inside* Neo4j only; they must never travel to the Python process.

Endpoints:
    GET /api/papers/{doi}  → full paper metadata with authors, venue, keywords
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status, Depends

from features.retrieval.models import PaperRead
from features.retrieval.service import RetrievalService
from core.dependencies import get_retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("/{doi:path}", response_model=PaperRead)
async def get_paper_by_doi(
    doi: str,
    retrieval_svc: RetrievalService = Depends(get_retrieval_service),
) -> PaperRead:
    """Fetch paper metadata from Neo4j by DOI.

    The DOI is captured as a path parameter (``{doi:path}``) to
    support the ``10.xxxx/yyyy`` format that contains slashes.

    Args:
        doi: The paper's DOI (e.g. ``10.1109/ACCESS.2023.1234567``).
        retrieval_svc: Injected RetrievalService (via FastAPI DI).

    Returns:
        Full paper metadata including authors, venue, and keywords.

    Raises:
        HTTPException 404: If no Paper node exists for this DOI.
    """
    paper = await retrieval_svc.get_paper(doi)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {doi}",
        )

    return paper
