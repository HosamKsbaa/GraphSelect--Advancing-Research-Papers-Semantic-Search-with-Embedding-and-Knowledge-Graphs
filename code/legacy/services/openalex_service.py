import re
import logging

import httpx

from models.openalex_models import Work, WorksResponse

logger = logging.getLogger(__name__)

BASE_URL: str = 'https://api.openalex.org'
DEFAULT_SELECT: str = (
    'id,doi,title,display_name,abstract_inverted_index,authorships,'
    'cited_by_count,publication_date,publication_year,type,'
    'referenced_works,primary_location,open_access,ids'
)


class OpenAlexService:
    """Service for interacting with the OpenAlex API.

    Provides methods to fetch paper metadata, citations, references,
    and reconstruct abstracts from inverted indexes.
    Ported from Dart OpenAlexService.
    """

    def __init__(self, email: str | None = None) -> None:
        self._email: str | None = email
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=120.0,
            headers={
                'User-Agent': f'ALRS-Python (mailto:{email})' if email else 'ALRS-Python',
            },
        )

    async def get_work(self, work_id: str) -> Work:
        """Fetch a single work by DOI or OpenAlex ID.

        Supports DOI, OpenAlex ID (W...), and PMID formats.
        Auto-prefixes 'doi:' if needed.
        """
        formatted_id: str = work_id
        if not (work_id.startswith('doi:') or work_id.startswith('W') or work_id.startswith('pmid:')):
            formatted_id = f'doi:{work_id}'

        logger.info(f'Fetching work: {formatted_id}')

        response: httpx.Response = await self._client.get(
            f'/works/{formatted_id}',
            params={'select': DEFAULT_SELECT},
        )
        response.raise_for_status()

        work = Work.model_validate(response.json())
        logger.info(f'Work fetched: {work.title}')
        return work

    async def get_citations(
        self,
        work_id: str,
        page: int = 1,
        per_page: int = 25,
        sort: str = 'cited_by_count:desc',
    ) -> WorksResponse:
        """Get papers that cite the given work (incoming citations)."""
        openalex_id: str = work_id if work_id.startswith('W') else f'W{work_id}'

        logger.info(f'Fetching citations for: {openalex_id} (page {page})')

        response: httpx.Response = await self._client.get(
            '/works',
            params={
                'filter': f'cites:{openalex_id}',
                'select': DEFAULT_SELECT,
                'sort': sort,
                'page': page,
                'per_page': per_page,
            },
        )
        response.raise_for_status()

        works_response = WorksResponse.model_validate(response.json())
        logger.info(f'Found {works_response.meta.count if works_response.meta else 0} citations')
        return works_response

    async def get_references(
        self,
        work_id: str,
        page: int = 1,
        per_page: int = 25,
        sort: str = 'cited_by_count:desc',
    ) -> WorksResponse:
        """Get papers cited by the given work (outgoing references)."""
        openalex_id: str = work_id if work_id.startswith('W') else f'W{work_id}'

        logger.info(f'Fetching references for: {openalex_id} (page {page})')

        response: httpx.Response = await self._client.get(
            '/works',
            params={
                'filter': f'cited_by:{openalex_id}',
                'select': DEFAULT_SELECT,
                'sort': sort,
                'page': page,
                'per_page': per_page,
            },
        )
        response.raise_for_status()

        works_response = WorksResponse.model_validate(response.json())
        logger.info(f'Found {works_response.meta.count if works_response.meta else 0} references')
        return works_response

    async def batch_get_works(self, dois: list[str]) -> WorksResponse:
        """Batch fetch multiple works by DOI (up to 100)."""
        if not dois:
            raise ValueError('DOI list cannot be empty')
        if len(dois) > 100:
            raise ValueError('Cannot fetch more than 100 works at once')

        formatted_dois: list[str] = []
        for doi in dois:
            if doi.startswith('https://doi.org/'):
                formatted_dois.append(doi)
            elif doi.startswith('doi:'):
                formatted_dois.append(f'https://doi.org/{doi[4:]}')
            else:
                formatted_dois.append(f'https://doi.org/{doi}')

        filter_str: str = f'doi:{"|".join(formatted_dois)}'

        response: httpx.Response = await self._client.get(
            '/works',
            params={
                'filter': filter_str,
                'select': DEFAULT_SELECT,
                'per_page': len(dois),
            },
        )
        response.raise_for_status()
        return WorksResponse.model_validate(response.json())

    @staticmethod
    def reconstruct_abstract(inverted_index: dict[str, list[int]]) -> str:
        """Reconstruct abstract text from OpenAlex inverted index format.

        OpenAlex stores abstracts as inverted indexes:
        {"word": [pos1, pos2], "another": [pos3]}

        This reconstructs the original text by mapping positions to words.
        """
        position_to_word: dict[int, str] = {}

        for word, positions in inverted_index.items():
            for pos in positions:
                position_to_word[pos] = word

        sorted_positions: list[int] = sorted(position_to_word.keys())
        words: list[str] = [position_to_word[pos] for pos in sorted_positions]

        return ' '.join(words)

    @staticmethod
    def extract_openalex_id(work: Work) -> str | None:
        """Extract OpenAlex ID (W...) from a Work's full URL."""
        if work.id is None:
            return None
        match = re.search(r'W\d+', work.id)
        return match.group(0) if match else None

    @staticmethod
    def extract_doi(work: Work) -> str | None:
        """Extract clean DOI without https://doi.org/ prefix."""
        if work.doi is None:
            return None
        if work.doi.startswith('https://doi.org/'):
            return work.doi[16:]
        return work.doi

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
