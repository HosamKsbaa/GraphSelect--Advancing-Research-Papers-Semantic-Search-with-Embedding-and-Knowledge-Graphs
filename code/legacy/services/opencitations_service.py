import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BASE_URL: str = 'https://opencitations.net'


class CitationRecord(BaseModel):
    """A citation record from OpenCitations."""

    oci: str | None = None
    citing: str | None = None
    cited: str | None = None
    creation: str | None = None
    timespan: str | None = None
    journal_sc: str | None = None
    author_sc: str | None = None


class MetadataRecord(BaseModel):
    """Paper metadata from OpenCitations."""

    doi: str | None = None
    title: str | None = None
    author: str | None = None
    year: str | None = None
    source_title: str | None = None
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    citation_count: str | None = None
    reference: str | None = None


class OpenCitationsService:
    """Service for interacting with the OpenCitations API.

    Ported from Dart ResearchService.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=120.0,
            headers={'User-Agent': 'ALRS-Python'},
        )

    async def get_paper_metadata(self, doi: str) -> list[MetadataRecord]:
        """Fetch metadata for a given DOI."""
        formatted_id: str = doi if doi.startswith('doi:') else f'doi:{doi}'
        logger.info(f'Fetching metadata for: {formatted_id}')

        response: httpx.Response = await self._client.get(
            f'/meta/v1/metadata/{formatted_id}'
        )
        response.raise_for_status()
        return [MetadataRecord.model_validate(r) for r in response.json()]

    async def get_citations(self, doi: str) -> list[CitationRecord]:
        """Fetch citations (papers that cite this paper) for a given DOI."""
        formatted_id: str = doi if doi.startswith('doi:') else f'doi:{doi}'
        logger.info(f'Fetching citations for: {formatted_id}')

        response: httpx.Response = await self._client.get(
            f'/index/v2/citations/{formatted_id}'
        )
        response.raise_for_status()
        return [CitationRecord.model_validate(r) for r in response.json()]

    async def get_references(self, doi: str) -> list[CitationRecord]:
        """Fetch references (papers cited by this paper) for a given DOI."""
        formatted_id: str = doi if doi.startswith('doi:') else f'doi:{doi}'
        logger.info(f'Fetching references for: {formatted_id}')

        response: httpx.Response = await self._client.get(
            f'/index/v2/references/{formatted_id}'
        )
        response.raise_for_status()
        return [CitationRecord.model_validate(r) for r in response.json()]

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
