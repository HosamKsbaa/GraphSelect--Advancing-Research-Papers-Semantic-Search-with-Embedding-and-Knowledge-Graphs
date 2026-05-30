"""Paper lookup API endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from models.paper import PaperRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("/{doi:path}", response_model=PaperRead)
async def get_paper_by_doi(doi: str) -> PaperRead:
    """Fetch paper metadata from Neo4j by DOI.

    The embedding field is NEVER included in the response (zero RAM policy).
    """
    from main import neo4j_service

    if neo4j_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j service not initialized",
        )

    # Query paper WITHOUT embedding field
    records = await neo4j_service.execute_read(
        """MATCH (p:Paper {doi: $doi})
           OPTIONAL MATCH (p)<-[:AUTHORED]-(a:Author)
           OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
           OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
           RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract,
                  p.year AS year, p.cited_by_count AS cited_by_count,
                  p.openalex_id AS openalex_id,
                  p.publication_date AS publication_date,
                  p.source AS source, p.created_at AS created_at,
                  collect(DISTINCT {name: a.name, openalex_id: a.openalex_id}) AS authors,
                  v.name AS venue_name,
                  collect(DISTINCT k.term) AS keywords""",
        {"doi": doi},
    )

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {doi}",
        )

    record = records[0]
    from models.paper import AuthorRead, VenueRead

    authors: list[AuthorRead] = []
    raw_authors = record.get("authors", [])
    if isinstance(raw_authors, list):
        for a in raw_authors:
            if isinstance(a, dict) and a.get("name"):
                authors.append(
                    AuthorRead(
                        name=str(a["name"]),
                        openalex_id=str(a["openalex_id"]) if a.get("openalex_id") else None,
                    )
                )

    venue: VenueRead | None = None
    if record.get("venue_name"):
        venue = VenueRead(name=str(record["venue_name"]))

    keywords_raw = record.get("keywords", [])
    keywords: list[str] = [str(k) for k in keywords_raw if k] if isinstance(keywords_raw, list) else []

    return PaperRead(
        doi=str(record["doi"]),
        title=str(record.get("title", "")),
        abstract=str(record["abstract"]) if record.get("abstract") else None,
        year=record.get("year"),  # type: ignore[arg-type]
        cited_by_count=int(record.get("cited_by_count", 0)),
        openalex_id=str(record["openalex_id"]) if record.get("openalex_id") else None,
        publication_date=str(record["publication_date"]) if record.get("publication_date") else None,
        source=str(record.get("source", "openalex")),
        authors=authors,
        venue=venue,
        keywords=keywords,
    )
