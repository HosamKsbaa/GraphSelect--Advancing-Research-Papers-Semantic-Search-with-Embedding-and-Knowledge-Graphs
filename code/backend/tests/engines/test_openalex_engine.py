"""Exercise the OpenAlex engine at its external HTTP boundary (ported from archive test_openalex_provider.py)."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from engines.openalex import MissingDoiError, OpenAlexClient, OpenAlexWork, ProviderBudget, ProviderError
from engines.papers import RetractionStatus


HttpHandler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def provider_work(work_id: str = "W1", doi: str | None = "10.1000/seed") -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{work_id}", "doi": doi,
        "title": "A real provider response fixture", "publication_year": 2025,
        "referenced_works": [], "cited_by_count": 12,
        "abstract_inverted_index": None,
    }


@pytest.mark.asyncio
async def test_doi_lookup_uses_bearer_auth_and_normalized_identifier() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=provider_work())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        client = OpenAlexClient(api_key="test-secret", email="owner@example.org", http_client=http_client)
        budget = ProviderBudget()
        work = await client.fetch_work("HTTPS://DOI.ORG/10.1000/SEED", budget)
    assert work.doi == "10.1000/seed"
    assert requests[0].url.path == "/works/doi:10.1000/seed"
    assert requests[0].headers["Authorization"] == "Bearer test-secret"
    assert "test-secret" not in str(requests[0].url)
    assert "owner@example.org" in requests[0].headers["User-Agent"]
    assert budget.requests_used == 1


@pytest.mark.asyncio
async def test_title_search_skips_no_doi_and_deduplicates_candidates() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search.title"] == "Paper title"
        assert request.url.params["per_page"] == "10"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"results": [
            provider_work("W1", None), provider_work("W2", "10.1000/A"),
            provider_work("W3", "https://doi.org/10.1000/a"),
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        papers = await OpenAlexClient(http_client=http_client).search_title(" Paper title ")
    assert [paper.doi for paper in papers] == ["10.1000/a"]
    assert papers[0].abstract is None
    assert papers[0].retraction_status is RetractionStatus.UNKNOWN


@pytest.mark.asyncio
async def test_reference_batch_retains_missing_doi_work_and_raw_metadata() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["filter"] == "openalex:W1|W2"
        assert request.url.params["per_page"] == "100"
        work = provider_work("W1", None)
        work["open_access"] = {"oa_status": "green", "oa_url": "https://example.org/paper"}
        return httpx.Response(200, json={"results": [work]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        works = await OpenAlexClient(http_client=http_client).fetch_works(
            ["https://openalex.org/W1", "w2", "W1"], ProviderBudget(),
        )
    assert works[0].doi is None
    assert works[0].id == "https://openalex.org/W1"
    assert works[0].model_dump(mode="json")["open_access"]["oa_status"] == "green"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected_code", [
    (404, "provider_not_found"), (401, "provider_authentication"),
    (403, "provider_authentication"), (400, "provider_rejected_request"),
])
async def test_non_retryable_provider_errors_are_sanitized(status: int, expected_code: str) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="secret-key-in-an-untrusted-body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == expected_code
    assert "secret-key" not in str(failure.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_throttling_retries_at_most_twice_and_records_every_attempt() -> None:
    attempts: list[int] = []
    calls = 0

    async def persist_attempt(count: int, elapsed: float) -> None:
        attempts.append(count)

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert attempts == list(range(1, calls + 1))
        return httpx.Response(429, headers={"Retry-After": "0"})

    budget = ProviderBudget(on_attempt=persist_attempt)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError, match="rate or usage limits"):
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", budget)
    assert calls == 3
    assert budget.requests_used == 3


@pytest.mark.asyncio
async def test_retry_success_consumes_the_shared_budget() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json=provider_work())

    budget = ProviderBudget(requests_used=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", budget)
    assert budget.requests_used == 4


@pytest.mark.asyncio
async def test_request_limit_stops_a_retry_before_another_http_request() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "0"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work(
                "10.1000/seed", ProviderBudget(max_requests=1),
            )
    assert failure.value.code == "request_limit"
    assert calls == 1


@pytest.mark.asyncio
async def test_elapsed_time_restores_without_counting_restart_downtime() -> None:
    budget = ProviderBudget(max_seconds=30, active_seconds=29.9, requests_used=4)
    assert 0 < budget.remaining_seconds() <= 0.1
    await budget.reserve_request()
    assert budget.requests_used == 5


@pytest.mark.asyncio
async def test_retry_after_cannot_exceed_active_time_limit() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "60"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == "time_limit"


@pytest.mark.asyncio
async def test_timeout_error_does_not_expose_the_http_exception() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("credential-and-url-must-not-leak", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work(
                "10.1000/seed", ProviderBudget(max_retries=0),
            )
    assert failure.value.code == "provider_timeout"
    assert "credential" not in str(failure.value)


@pytest.mark.asyncio
async def test_active_deadline_interrupts_a_slow_external_request() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json=provider_work())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work(
                "10.1000/seed", ProviderBudget(max_seconds=0.02, max_retries=0),
            )
    assert failure.value.code == "provider_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"doi": "10.1000/seed", "title": "Identity missing"},
    {"id": "https://openalex.org/W1", "doi": "openalex:W1"},
    {"id": "https://openalex.org/W1", "abstract_inverted_index": {"word": [-1]}},
    ["not-a-work"],
])
async def test_malformed_records_fail_instead_of_becoming_papers(body: object) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_non_json_response_is_reported_explicitly() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Gateway message</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_same_origin_merged_work_redirect_counts_against_budget() -> None:
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if len(paths) == 1:
            return httpx.Response(301, headers={"Location": "/works/W2"})
        return httpx.Response(200, json=provider_work("W2"))

    budget = ProviderBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        work = await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", budget)
    assert paths == ["/works/doi:10.1000/seed", "/works/W2"]
    assert work.id == "https://openalex.org/W2"
    assert budget.requests_used == 2


@pytest.mark.asyncio
async def test_external_redirect_never_receives_provider_credentials() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(301, headers={"Location": "https://other.example/work"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(api_key="secret", http_client=http_client).fetch_work(
                "10.1000/seed", ProviderBudget(),
            )
    assert failure.value.code == "invalid_response"
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_attempt_persistence_prevents_http_work() -> None:
    calls = 0

    async def reject_persistence(count: int, elapsed: float) -> None:
        raise RuntimeError("Persistent storage unavailable")

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=provider_work())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(RuntimeError, match="Persistent storage unavailable"):
            await OpenAlexClient(http_client=http_client).fetch_work(
                "10.1000/seed", ProviderBudget(on_attempt=reject_persistence),
            )
    assert calls == 0


@pytest.mark.asyncio
async def test_cancellation_records_attempt_usage_and_propagates() -> None:
    started = asyncio.Event()
    usage: list[tuple[int, float]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=provider_work())

    async def save_usage(count: int, elapsed: float) -> None:
        usage.append((count, elapsed))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        task = asyncio.create_task(OpenAlexClient(http_client=http_client).fetch_work(
            "10.1000/seed", ProviderBudget(on_usage=save_usage),
        ))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert usage[0][0] == 1
    assert usage[0][1] > 0


@pytest.mark.asyncio
async def test_transport_is_explicit_and_is_not_constructed_implicitly() -> None:
    client = OpenAlexClient()
    assert client.http_client is None
    with pytest.raises(ProviderError) as failure:
        await client.fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == "provider_not_configured"


def test_missing_doi_cannot_use_provider_identifier_as_paper_identity() -> None:
    with pytest.raises(MissingDoiError):
        OpenAlexClient().work_to_paper(OpenAlexWork.model_validate(provider_work("W1", None)))


@pytest.mark.parametrize("explicit_null", [False, True])
def test_missing_citation_count_remains_unknown_without_dated_observation(explicit_null: bool) -> None:
    raw_work = provider_work()
    raw_work.pop("cited_by_count")
    if explicit_null:
        raw_work["cited_by_count"] = None
    work = OpenAlexWork.model_validate(raw_work)
    paper = OpenAlexClient().work_to_paper(work)
    assert work.cited_by_count is None
    assert paper.citation_count is None
    assert paper.dated_citations == []
    assert paper.retrieved_at is not None
    assert paper.retrieved_at.utcoffset() is not None


def test_explicit_zero_citation_count_is_a_known_dated_observation() -> None:
    raw_work = provider_work()
    raw_work["cited_by_count"] = 0
    paper = OpenAlexClient().parse_work_to_paper(raw_work)
    assert paper.citation_count == 0
    assert paper.dated_citations[0].citation_count == 0


def test_legacy_fixture_parser_preserves_metadata_without_http() -> None:
    raw_work = provider_work()
    raw_work.update({
        "doi": "HTTPS://DOI.ORG/10.1000/SEED", "is_retracted": True,
        "abstract_inverted_index": {"evidence": [1], "Useful": [0]},
        "authorships": [{"author": {"id": "A1", "display_name": "Researcher"},
                        "institutions": [{"display_name": "University"}]}],
        "primary_location": {"source": {"display_name": "Journal", "issn_l": "1234-5678"}},
    })
    paper = OpenAlexClient().parse_work_to_paper(raw_work)
    assert paper.doi == "10.1000/seed"
    assert paper.abstract == "Useful evidence"
    assert paper.authors[0].affiliation == "University"
    assert paper.venue is not None and paper.venue.name == "Journal"
    assert paper.retraction_status is RetractionStatus.RETRACTED
    assert paper.dated_citations[0].citation_count == 12

@pytest.mark.asyncio
async def test_retry_allowance_is_shared_across_logical_calls_and_resume() -> None:
    calls = 0
    saved_retries: list[int] = []

    async def save_retries(count: int) -> None:
        saved_retries.append(count)

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls in (1, 2, 4):
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json=provider_work())

    budget = ProviderBudget(on_retry=save_retries)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        client = OpenAlexClient(http_client=http_client)
        await client.fetch_work("10.1000/seed", budget)
        resumed_budget = ProviderBudget(
            requests_used=budget.requests_used, retries_used=budget.retries_used,
            active_seconds=budget.active_seconds, on_retry=save_retries,
        )
        with pytest.raises(ProviderError) as failure:
            await client.fetch_work("10.1000/other", resumed_budget)
    assert failure.value.code == "provider_unavailable"
    assert calls == 4
    assert saved_retries == [1, 2]
    assert resumed_budget.retries_used == 2


@pytest.mark.asyncio
async def test_batch_limit_rejects_oversized_input_before_http() -> None:
    client = OpenAlexClient()
    with pytest.raises(ValueError, match="at most 50"):
        await client.fetch_works([f"W{index}" for index in range(51)], ProviderBudget())

@pytest.mark.asyncio
async def test_selected_doi_cannot_be_replaced_by_an_unrelated_work() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_work("W2", "10.1000/unrelated"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.1000/seed", ProviderBudget())
    assert failure.value.code == "provider_doi_mismatch"


@pytest.mark.asyncio
async def test_captured_arxiv_alias_response_reports_canonical_doi_mismatch() -> None:
    response_bytes = (Path(__file__).parent / "fixtures/openalex_attention_canonical_work.json").read_bytes()

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=response_bytes, headers={"Content-Type": "application/json"})

    work = OpenAlexWork.model_validate_json(response_bytes)
    assert work.id == "https://openalex.org/W2626778328"
    assert work.title == "Attention Is All You Need"
    assert work.doi == "10.65215/2q58a426"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_work("10.48550/arxiv.1706.03762", ProviderBudget())
    assert failure.value.code == "provider_doi_mismatch"


@pytest.mark.asyncio
async def test_captured_work_can_be_fetched_using_its_selected_canonical_doi() -> None:
    response_bytes = (Path(__file__).parent / "fixtures/openalex_attention_canonical_work.json").read_bytes()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works/doi:10.65215/2q58a426"
        return httpx.Response(200, content=response_bytes, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        work = await OpenAlexClient(http_client=http_client).fetch_work("10.65215/2q58a426", ProviderBudget())
    assert work.doi == "10.65215/2q58a426"
    assert len(work.referenced_works) == 28


@pytest.mark.asyncio
async def test_reference_batch_rejects_records_outside_approved_identifiers() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [provider_work("W999")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ProviderError) as failure:
            await OpenAlexClient(http_client=http_client).fetch_works(["W2"], ProviderBudget())
    assert failure.value.code == "invalid_response"
