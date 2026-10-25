"""Asynchronous, bounded OpenAlex discovery with truthful metadata parsing."""

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from engines.papers import Author, DatedCitationCount, Paper, RetractionStatus, Venue
from .models import OpenAlexWork, OpenAlexWorkPage, normalize_doi, normalize_work_id
from engines.errors import ProviderError
from .budget import ProviderBudget
from .rate_limiter import AsyncTokenBucketRateLimiter


class MissingDoiError(ValueError):
    """An external work without a DOI cannot become a DOI-keyed paper."""


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positioned_words: list[tuple[int, str]] = []
    for word, positions in index.items():
        positioned_words.extend((position, word) for position in positions)
    positioned_words.sort()
    return " ".join(word for _, word in positioned_words)


def parse_authors(work: OpenAlexWork) -> list[Author]:
    authors = []
    for authorship in work.authorships:
        if not authorship.author.display_name:
            continue
        affiliation = None
        if authorship.institutions:
            affiliation = authorship.institutions[0].display_name
        authors.append(Author(
            name=authorship.author.display_name,
            affiliation=affiliation,
            openalex_id=authorship.author.id,
        ))
    return authors


def parse_venue(work: OpenAlexWork) -> Venue | None:
    if work.primary_location is None or work.primary_location.source is None:
        return None
    source = work.primary_location.source
    if source.display_name is None:
        return None
    return Venue(
        name=source.display_name, issn=source.issn_l,
        openalex_id=source.id, is_oa=source.is_oa,
    )


def parse_retraction_status(flag: bool | None) -> RetractionStatus:
    if flag is True:
        return RetractionStatus.RETRACTED
    if flag is False:
        return RetractionStatus.NO_NOTICE_FOUND
    return RetractionStatus.UNKNOWN


def dated_citation_observations(work: OpenAlexWork) -> list[DatedCitationCount]:
    if work.cited_by_count is None:
        return []
    return [DatedCitationCount(
        observed_at=datetime.now(timezone.utc), citation_count=work.cited_by_count,
        source_version="openalex-api-v1",
    )]


class OpenAlexClient:
    def __init__(
        self,
        api_key: str | None = None,
        email: str | None = None,
        base_url: str = "https://api.openalex.org",
        rate_limiter: AsyncTokenBucketRateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.email = email
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.rate_limiter = rate_limiter or AsyncTokenBucketRateLimiter(rate=10.0, capacity=10.0)

    def _build_headers(self) -> dict[str, str]:
        identity = "ALRS-Backend/3.0"
        if self.email:
            identity += f" (mailto:{self.email})"
        headers = {"User-Agent": identity, "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def parse_work_to_paper(self, item: dict[str, Any]) -> Paper:
        """Keep fixture parsing available without constructing a network client."""
        return self.work_to_paper(OpenAlexWork.model_validate(item))

    def work_to_paper(self, work: OpenAlexWork) -> Paper:
        if work.doi is None:
            raise MissingDoiError("The OpenAlex work has no DOI and cannot be ingested as a paper.")
        return Paper(
            doi=work.doi,
            title=work.title or work.display_name or "Untitled",
            abstract=reconstruct_abstract(work.abstract_inverted_index),
            year=work.publication_year,
            authors=parse_authors(work),
            venue=parse_venue(work),
            citation_count=work.cited_by_count,
            retrieved_at=datetime.now(timezone.utc),
            dated_citations=dated_citation_observations(work),
            retraction_status=parse_retraction_status(work.is_retracted),
            is_retracted=work.is_retracted,
            topics=[topic.display_name for topic in work.topics if topic.display_name],
            openalex_id=work.id,
        )

    async def fetch_work(self, doi: str, budget: ProviderBudget) -> OpenAlexWork:
        clean_doi = normalize_doi(doi)
        data = await self._request_json(f"/works/doi:{quote(clean_doi, safe='/')}", {}, budget)
        try:
            work = OpenAlexWork.model_validate(data)
            self._require_provider_identity(work)
        except (ValidationError, ValueError):
            raise ProviderError("invalid_response", "OpenAlex returned an invalid work record.") from None
        if work.doi is not None and work.doi != clean_doi:
            raise ProviderError("provider_doi_mismatch", "OpenAlex returned a different canonical DOI; select its current record before discovery.")
        return work

    async def fetch_works(self, ids: list[str], budget: ProviderBudget) -> list[OpenAlexWork]:
        work_ids = list(dict.fromkeys(normalize_work_id(value) for value in ids))
        if not work_ids:
            return []
        if len(work_ids) > 50:
            raise ValueError("Fetch at most 50 OpenAlex work identifiers per batch.")
        data = await self._request_json("/works", {
            "filter": "openalex:" + "|".join(work_ids), "per_page": "100",
        }, budget)
        works = self._parse_work_page(data)
        for work in works:
            if work.id is None or normalize_work_id(work.id) not in work_ids:
                raise ProviderError("invalid_response", "OpenAlex returned a work outside the requested identifier batch.")
        return works

    async def fetch_citing_works(
        self, work_id: str, budget: ProviderBudget, cursor: str = "*", page_size: int = 50,
    ) -> OpenAlexWorkPage:
        if type(page_size) is not int or not 1 <= page_size <= 50:
            raise ValueError("A citation page must contain from 1 to 50 records")
        identifier = normalize_work_id(work_id)
        data = await self._request_json("/works", {
            "filter": "cites:" + identifier, "per_page": str(page_size), "cursor": cursor,
        }, budget)
        works = self._parse_work_page(data)
        if len(works) > page_size:
            raise ProviderError("invalid_response", "OpenAlex returned more citation records than requested.")
        page = OpenAlexWorkPage.model_validate(data)
        if any(identifier not in [normalize_work_id(item) for item in work.referenced_works]
               for work in works):
            raise ProviderError("invalid_response", "OpenAlex returned a work outside the requested citation relationship.")
        return page

    async def search_title(self, title: str, max_results: int = 10) -> list[Paper]:
        if not title.strip() or not 1 <= max_results <= 100:
            raise ValueError("Provide a title and a result limit from 1 to 100.")
        data = await self._request_json("/works", {
            "search.title": title.strip(), "per_page": str(max_results),
        }, ProviderBudget())
        papers = []
        seen_dois: set[str] = set()
        for work in self._parse_work_page(data):
            # No-DOI works remain provider records, never synthesized paper identities.
            if work.doi is None or work.doi in seen_dois:
                continue
            seen_dois.add(work.doi)
            papers.append(self.work_to_paper(work))
        return papers

    async def search_works(
        self, query: str, budget: ProviderBudget, max_results: int = 10,
    ) -> list[OpenAlexWork]:
        """General research search; retain missing DOI records for search receipts."""
        if not query.strip() or not 1 <= max_results <= 10:
            raise ValueError("Provide a query and a result limit from 1 to 10.")
        data = await self._request_json("/works", {
            "search": query.strip(), "per_page": str(max_results),
        }, budget)
        works = self._parse_work_page(data)
        if len(works) > max_results:
            raise ProviderError("invalid_response", "OpenAlex returned more search records than requested.")
        return works

    def _parse_work_page(self, data: object) -> list[OpenAlexWork]:
        try:
            page = OpenAlexWorkPage.model_validate(data)
            for work in page.results:
                self._require_provider_identity(work)
        except (ValidationError, ValueError):
            raise ProviderError("invalid_response", "OpenAlex returned an invalid work listing.") from None
        return page.results

    @staticmethod
    def _require_provider_identity(work: OpenAlexWork) -> None:
        if work.id is None:
            raise ValueError("Provider records must include their OpenAlex identifier.")

    async def _request_json(self, path: str, parameters: dict[str, str], budget: ProviderBudget) -> object:
        url = httpx.URL(self.base_url + path)
        while True:
            response, error = await self._attempt_response(url, parameters, budget)
            if response is not None:
                if response.is_redirect:
                    url = self._redirect_url(response)
                    continue
                if not response.is_error:
                    return self._decode_json(response)
                error = self._response_error(response.status_code)
            assert error is not None
            if not error.retryable or budget.retries_used >= budget.max_retries:
                raise error
            await self._wait_to_retry(response, budget)

    async def _attempt_response(
        self, url: httpx.URL, parameters: dict[str, str], budget: ProviderBudget,
    ) -> tuple[httpx.Response | None, ProviderError | None]:
        try:
            return await self._get_response(url, parameters, budget), None
        except (httpx.TimeoutException, TimeoutError):
            return None, ProviderError(
                "provider_timeout", "OpenAlex did not respond within the time limit.", retryable=True,
            )
        except httpx.TransportError:
            return None, ProviderError(
                "provider_unavailable", "OpenAlex could not be reached.", retryable=True,
            )

    async def _get_response(self, url: httpx.URL, parameters: dict[str, str], budget: ProviderBudget) -> httpx.Response:
        if self.http_client is None:
            raise ProviderError("provider_not_configured", "OpenAlex requires an application-owned HTTP client.")
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                await self.rate_limiter.acquire()
                await budget.reserve_request()
                remaining = budget.remaining_seconds()
                return await self.http_client.get(
                    url, params=parameters, headers=self._build_headers(),
                    timeout=remaining, follow_redirects=False,
                )
        finally:
            await budget.persist_usage()

    @staticmethod
    def _decode_json(response: httpx.Response) -> object:
        try:
            data: object = response.json()
        except ValueError:
            raise ProviderError("invalid_response", "OpenAlex returned a non-JSON response.") from None
        return data

    def _redirect_url(self, response: httpx.Response) -> httpx.URL:
        location = response.headers.get("Location")
        if location is None:
            raise ProviderError("invalid_response", "OpenAlex returned a redirect without a destination.")
        destination = response.request.url.join(location)
        origin = httpx.URL(self.base_url)
        if (destination.scheme, destination.host, destination.port) != (origin.scheme, origin.host, origin.port):
            raise ProviderError("invalid_response", "OpenAlex returned an unexpected redirect destination.")
        return destination.copy_with(query=None)

    @staticmethod
    def _response_error(status: int) -> ProviderError:
        if status == 404:
            return ProviderError("provider_not_found", "The requested work was not found in OpenAlex.")
        if status in (401, 403):
            return ProviderError("provider_authentication", "OpenAlex rejected the configured credentials.")
        if status == 429:
            return ProviderError("provider_rate_limited", "OpenAlex rejected the request because of rate or usage limits.", retryable=True)
        if status in (408, 500, 502, 503, 504):
            return ProviderError("provider_unavailable", "OpenAlex is temporarily unavailable.", retryable=True)
        return ProviderError("provider_rejected_request", f"OpenAlex rejected the request with HTTP status {status}.")

    async def _wait_to_retry(self, response: httpx.Response | None, budget: ProviderBudget) -> None:
        budget.check_request_available()
        delay = self._retry_delay(response, budget.retries_used)
        if delay >= budget.remaining_seconds():
            raise ProviderError("time_limit", "Retrying would exceed the provider active-time limit.")
        await budget.reserve_retry()
        try:
            await asyncio.sleep(delay)
        finally:
            await budget.persist_usage()

    @staticmethod
    def _retry_delay(response: httpx.Response | None, retries_used: int) -> float:
        if response is None or "Retry-After" not in response.headers:
            return 0.25 * (2.0 ** retries_used)
        value = response.headers["Retry-After"]
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                return 0.25 * (2.0 ** retries_used)
