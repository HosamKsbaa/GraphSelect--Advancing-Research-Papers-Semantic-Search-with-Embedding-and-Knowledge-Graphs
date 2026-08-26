"""OpenAlex API client with api_key authentication and rate limiting."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from features.retrieval.models import PaperCreate, PaperSummary

if TYPE_CHECKING:
    from core.logging.log_service import LogService
    from core.clients.rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org"


class OpenAlexService:
    """Client for the OpenAlex API.

    Uses api_key query parameter authentication (polite pool deprecated Feb 2026).
    Integrates with AdaptiveRateLimiter for automatic 429 backoff.
    """

    def __init__(
        self,
        api_key: str,
        rate_limiter: AdaptiveRateLimiter | None = None,
        log_service: LogService | None = None,
    ) -> None:
        # Detect placeholder keys and treat them as "no key"
        _placeholder_keys = {"", "your_openalex_api_key_here", "dev-dummy-openalex-key"}
        self._api_key = api_key if api_key not in _placeholder_keys else ""
        self._rate_limiter = rate_limiter
        self._log_service = log_service

        headers: dict[str, str] = {"Accept": "application/json"}
        if not self._api_key:
            # Use email-based polite pool for better rate limits without a key
            headers["User-Agent"] = "mailto:alrs-dev@example.com"
            logger.info("OpenAlex: no API key configured, using polite pool")
        else:
            logger.info("OpenAlex: using API key authentication")

        import os
        verify_ssl = True
        if os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"):
            verify_ssl = False
            logger.info("OpenAlex: detected HTTP proxy, disabling SSL verification for debugging")

        self._client = httpx.AsyncClient(
            base_url=OPENALEX_BASE_URL,
            timeout=30.0,
            headers=headers,
            verify=verify_ssl,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str | int] | None = None,
        session_id: str | None = None,
    ) -> dict[str, object]:
        """Make an authenticated, rate-limited request to OpenAlex.

        Args:
            method: HTTP method (GET, POST).
            path: API path (e.g., '/works/doi:10.1234/test').
            params: Query parameters.
            session_id: Session ID for log correlation.

        Returns:
            Parsed JSON response as dict.

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors.
        """
        import time
        import asyncio

        if params is None:
            params = {}
        if self._api_key:
            params["api_key"] = self._api_key

        url = f"{OPENALEX_BASE_URL}{path}"
        max_retries = 3

        for attempt in range(max_retries + 1):
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()

            start_ms = int(time.monotonic() * 1000)
            try:
                response = await self._client.request(method, path, params=params)
                elapsed_ms = int(time.monotonic() * 1000) - start_ms

                if self._log_service is not None:
                    # Truncate response_body if excessively large to avoid DB issues
                    resp_text = response.text
                    if len(resp_text) > 50000:
                        resp_text = resp_text[:50000] + "...[TRUNCATED]"
                        
                    await self._log_service.log_api_request(
                        service="OpenAlex",
                        method=method,
                        url=url,
                        status_code=response.status_code,
                        response_time_ms=elapsed_ms,
                        payload_summary=f"params={list(params.keys())}",
                        request_body=None,
                        response_body=resp_text,
                        session_id=session_id,
                    )

                if response.status_code == 429:
                    if self._rate_limiter is not None:
                        self._rate_limiter.on_429()
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()

                if self._rate_limiter is not None:
                    self._rate_limiter.on_success()

                response.raise_for_status()
                result: dict[str, object] = response.json()
                return result
            except Exception as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

                elapsed_ms = int(time.monotonic() * 1000) - start_ms
                status_code = getattr(getattr(exc, "response", None), "status_code", 500)
                if self._log_service is not None:
                    resp_text = getattr(getattr(exc, "response", None), "text", None)
                    if resp_text and len(resp_text) > 50000:
                        resp_text = resp_text[:50000] + "...[TRUNCATED]"
                        
                    await self._log_service.log_api_request(
                        service="OpenAlex",
                        method=method,
                        url=url,
                        status_code=status_code,
                        response_time_ms=elapsed_ms,
                        payload_summary=f"FAILED: {str(exc)}",
                        request_body=None,
                        response_body=resp_text,
                        session_id=session_id,
                    )
                raise exc
        
        raise RuntimeError("Unreachable")

    async def get_paper_by_doi(
        self,
        doi: str,
        session_id: str | None = None,
    ) -> PaperCreate | None:
        """Fetch a paper by DOI from OpenAlex.

        Args:
            doi: The DOI (e.g., '10.1145/3292500.3330919').
            session_id: Session ID for log correlation.

        Returns:
            PaperCreate model or None if not found.
        """
        try:
            data = await self._request(
                "GET",
                f"/works/doi:{doi}",
                session_id=session_id,
            )
            return self._parse_work(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Paper not found in OpenAlex: %s", doi)
                return None
            raise

    async def batch_get_papers_by_dois(
        self,
        dois: list[str],
        session_id: str | None = None,
    ) -> list[PaperCreate]:
        """Fetch multiple papers by DOIs efficiently.

        Chunks the requests in batches of 50 and uses the OR filter syntax.
        """
        if not dois:
            return []

        # Make unique and remove prefix
        clean_dois = list(set(doi.replace("https://doi.org/", "") for doi in dois))
        papers: list[PaperCreate] = []
        chunk_size = 50

        for i in range(0, len(clean_dois), chunk_size):
            chunk = clean_dois[i : i + chunk_size]
            joined_dois = "|".join(chunk)
            filter_val = f"doi:{joined_dois}"
            
            data = await self._request(
                "GET",
                "/works",
                params={
                    "filter": filter_val,
                    "per_page": len(chunk),
                },
                session_id=session_id,
            )
            
            results = data.get("results", [])
            for res in results:
                if isinstance(res, dict):
                    papers.append(self._parse_work(res))

        return papers

    async def search_by_title(
        self,
        title: str,
        max_results: int = 10,
        session_id: str | None = None,
    ) -> list[PaperSummary]:
        """Search for papers by title, returning a candidate list.

        Args:
            title: Search query string.
            max_results: Maximum number of results (1-25).
            session_id: Session ID for log correlation.

        Returns:
            List of PaperSummary models.
        """
        data = await self._request(
            "GET",
            "/works",
            params={
                "search": title,
                "per_page": min(max_results, 25),
                "select": "doi,title,publication_year,cited_by_count,authorships",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        candidates: list[PaperSummary] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
            author_names: list[str] = []
            for auth in authorships:
                author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
                name = author_info.get("display_name")
                if name is not None:
                    author_names.append(str(name))
            candidates.append(
                PaperSummary(
                    doi=doi_str,
                    title=str(work.get("title", "")),
                    year=work.get("publication_year"),  # type: ignore[arg-type]
                    cited_by_count=int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
                    authors=author_names[:5],
                )
            )
        return candidates

    async def search_by_author(
        self,
        author_name: str,
        max_results: int = 10,
        session_id: str | None = None,
    ) -> list[PaperSummary]:
        """Search for papers by a specific author name.

        Args:
            author_name: Full or partial author name (e.g. "Yoshua Bengio").
            max_results: Maximum number of results (1-25).
            session_id: Session ID for log correlation.

        Returns:
            List of PaperSummary models.
        """
        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": f"authorships.author.display_name.search:{author_name}",
                "per_page": min(max_results, 25),
                "select": "doi,title,publication_year,cited_by_count,authorships",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        candidates: list[PaperSummary] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
            author_names: list[str] = []
            for auth in authorships:
                author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
                name = author_info.get("display_name")
                if name is not None:
                    author_names.append(str(name))
            candidates.append(
                PaperSummary(
                    doi=doi_str,
                    title=str(work.get("title", "")),
                    year=work.get("publication_year"),  # type: ignore[arg-type]
                    cited_by_count=int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
                    authors=author_names[:5],
                )
            )
        return candidates

    async def search_by_venue(
        self,
        venue_name: str,
        max_results: int = 10,
        session_id: str | None = None,
    ) -> list[PaperSummary]:
        """Search for papers published in a specific venue (journal/conference).

        Args:
            venue_name: Name of the venue (e.g. "NeurIPS", "Nature").
            max_results: Maximum number of results (1-25).
            session_id: Session ID for log correlation.

        Returns:
            List of PaperSummary models sorted by citation count descending.
        """
        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": f"primary_location.source.display_name.search:{venue_name}",
                "per_page": min(max_results, 25),
                "select": "doi,title,publication_year,cited_by_count,authorships",
                "sort": "cited_by_count:desc",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        candidates: list[PaperSummary] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
            author_names: list[str] = []
            for auth in authorships:
                author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
                name = author_info.get("display_name")
                if name is not None:
                    author_names.append(str(name))
            candidates.append(
                PaperSummary(
                    doi=doi_str,
                    title=str(work.get("title", "")),
                    year=work.get("publication_year"),  # type: ignore[arg-type]
                    cited_by_count=int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
                    authors=author_names[:5],
                )
            )
        return candidates


    async def get_citations(
        self,
        doi: str,
        max_results: int = 200,
        session_id: str | None = None,
        openalex_id: str | None = None,
    ) -> list[str]:
        """Get DOIs of papers that cite the given paper.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of citing DOIs.
            session_id: Session ID for log correlation.
            openalex_id: The OpenAlex ID to use for robust filtering (e.g., 'W12345').

        Returns:
            List of citing paper DOIs.
        """
        filter_str = f"cites:doi:{doi}"
        if openalex_id:
            short_id = openalex_id.replace("https://openalex.org/", "")
            filter_str = f"cites:{short_id}"

        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": filter_str,
                "per_page": min(max_results, 200),
                "select": "doi",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        dois: list[str] = []
        for work in results:
            work_doi = work.get("doi")
            if work_doi is not None:
                dois.append(str(work_doi).replace("https://doi.org/", ""))
        return dois

    async def get_references(
        self,
        doi: str,
        max_results: int = 200,
        session_id: str | None = None,
        openalex_id: str | None = None,
    ) -> list[str]:
        """Get DOIs of papers referenced by the given paper.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of referenced DOIs.
            session_id: Session ID for log correlation.
            openalex_id: The OpenAlex ID to use for robust filtering (e.g., 'W12345').

        Returns:
            List of referenced paper DOIs.
        """
        filter_str = f"cited_by:doi:{doi}"
        if openalex_id:
            short_id = openalex_id.replace("https://openalex.org/", "")
            filter_str = f"cited_by:{short_id}"

        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": filter_str,
                "per_page": min(max_results, 200),
                "select": "doi",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
        dois: list[str] = []
        for work in results:
            work_doi = work.get("doi")
            if work_doi is not None:
                dois.append(str(work_doi).replace("https://doi.org/", ""))
        return dois

    @staticmethod
    def _reconstruct_abstract(abstract_inverted_index: dict[str, list[int]] | None) -> str | None:
        """Reconstruct the plain text abstract from OpenAlex's abstract_inverted_index."""
        if not abstract_inverted_index or not isinstance(abstract_inverted_index, dict):
            return None

        try:
            word_positions: list[tuple[int, str]] = []
            for word, positions in abstract_inverted_index.items():
                if isinstance(positions, list):
                    for pos in positions:
                        if isinstance(pos, int):
                            word_positions.append((pos, str(word)))

            if not word_positions:
                return None

            word_positions.sort(key=lambda x: x[0])
            return " ".join(word for _, word in word_positions)
        except Exception as e:
            logger.warning("Failed to reconstruct abstract from inverted index: %s", e)
            return None

    reconstruct_abstract = _reconstruct_abstract


    @staticmethod
    def _parse_work(data: dict[str, object]) -> PaperCreate:
        """Parse an OpenAlex work response into a PaperCreate model."""
        doi_raw = data.get("doi", "")
        doi = str(doi_raw).replace("https://doi.org/", "") if doi_raw else ""

        abstract = None
        if data.get("abstract"):
            abstract = str(data.get("abstract"))
        elif data.get("abstract_inverted_index"):
            abstract = OpenAlexService._reconstruct_abstract(
                data.get("abstract_inverted_index")  # type: ignore[arg-type]
            )

        return PaperCreate(
            doi=doi,
            title=str(data.get("title", "")),
            abstract=abstract,
            year=data.get("publication_year"),  # type: ignore[arg-type]
            cited_by_count=int(data.get("cited_by_count") or 0),  # type: ignore[arg-type]
            openalex_id=str(data.get("id", "")) if data.get("id") else None,
            publication_date=str(data.get("publication_date", ""))
            if data.get("publication_date")
            else None,
            referenced_works=data.get("referenced_works", []),  # type: ignore[arg-type]
            source="openalex",
        )
