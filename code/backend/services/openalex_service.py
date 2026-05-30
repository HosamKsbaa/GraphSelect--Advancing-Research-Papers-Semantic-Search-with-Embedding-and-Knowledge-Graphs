"""OpenAlex API client with api_key authentication and rate limiting."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from models.paper import PaperCreate, PaperSummary

if TYPE_CHECKING:
    from services.log_service import LogService
    from services.rate_limiter import AdaptiveRateLimiter

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
        self._api_key = api_key
        self._rate_limiter = rate_limiter
        self._log_service = log_service
        self._client = httpx.AsyncClient(
            base_url=OPENALEX_BASE_URL,
            timeout=30.0,
            headers={"Accept": "application/json"},
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

        if params is None:
            params = {}
        params["api_key"] = self._api_key

        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

        start_ms = int(time.monotonic() * 1000)
        url = f"{OPENALEX_BASE_URL}{path}"

        response = await self._client.request(method, path, params=params)
        elapsed_ms = int(time.monotonic() * 1000) - start_ms

        if self._log_service is not None:
            await self._log_service.log_api_request(
                service="openalex",
                method=method,
                url=url,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                payload_summary=f"params={list(params.keys())}",
                session_id=session_id,
            )

        if response.status_code == 429:
            if self._rate_limiter is not None:
                self._rate_limiter.on_429()
            response.raise_for_status()

        if self._rate_limiter is not None:
            self._rate_limiter.on_success()

        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result

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
        results: list[dict[str, object]] = data.get("results", [])  # type: ignore[assignment]
        candidates: list[PaperSummary] = []
        for work in results:
            doi = work.get("doi")
            if doi is None:
                continue
            doi_str = str(doi).replace("https://doi.org/", "")
            authorships: list[dict[str, object]] = work.get("authorships", [])  # type: ignore[assignment]
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
                    cited_by_count=int(work.get("cited_by_count", 0)),  # type: ignore[arg-type]
                    authors=author_names[:5],
                )
            )
        return candidates

    async def get_citations(
        self,
        doi: str,
        max_results: int = 200,
        session_id: str | None = None,
    ) -> list[str]:
        """Get DOIs of papers that cite the given paper.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of citing DOIs.
            session_id: Session ID for log correlation.

        Returns:
            List of citing paper DOIs.
        """
        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": f"cites:doi:{doi}",
                "per_page": min(max_results, 200),
                "select": "doi",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results", [])  # type: ignore[assignment]
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
    ) -> list[str]:
        """Get DOIs of papers referenced by the given paper.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of referenced DOIs.
            session_id: Session ID for log correlation.

        Returns:
            List of referenced paper DOIs.
        """
        data = await self._request(
            "GET",
            "/works",
            params={
                "filter": f"cited_by:doi:{doi}",
                "per_page": min(max_results, 200),
                "select": "doi",
            },
            session_id=session_id,
        )
        results: list[dict[str, object]] = data.get("results", [])  # type: ignore[assignment]
        dois: list[str] = []
        for work in results:
            work_doi = work.get("doi")
            if work_doi is not None:
                dois.append(str(work_doi).replace("https://doi.org/", ""))
        return dois

    @staticmethod
    def _parse_work(data: dict[str, object]) -> PaperCreate:
        """Parse an OpenAlex work response into a PaperCreate model."""
        doi_raw = data.get("doi", "")
        doi = str(doi_raw).replace("https://doi.org/", "") if doi_raw else ""

        return PaperCreate(
            doi=doi,
            title=str(data.get("title", "")),
            abstract=str(data.get("abstract", "")) if data.get("abstract") else None,
            year=data.get("publication_year"),  # type: ignore[arg-type]
            cited_by_count=int(data.get("cited_by_count", 0)),  # type: ignore[arg-type]
            openalex_id=str(data.get("id", "")) if data.get("id") else None,
            publication_date=str(data.get("publication_date", ""))
            if data.get("publication_date")
            else None,
            source="openalex",
        )
