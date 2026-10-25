"""Exercise the embeddings engine at the native Gemini SDK boundary.

The first three tests are ported from archive `test_full_alrs_search_contracts.py`
(commit 865cd08); only imports changed. The text-format test is new.
"""
import math

import httpx
import json
import pytest
from google import genai
from google.genai.types import HttpOptions

from engines.embeddings import GeminiEmbeddingClient, document_text, normalize_embedding, query_text
from engines.errors import ProviderError


def test_embedding_normalizes_and_rejects_corrupt_vectors() -> None:
    normalized = normalize_embedding([3,4]+[0]*766)
    assert normalized[:2] == [0.6,0.8]
    assert math.sqrt(sum(value*value for value in normalized)) == pytest.approx(1)
    for invalid in ([0]*768,[float("nan")]+[0]*767,[1,2]):
        with pytest.raises(ProviderError,match="embedding"):
            normalize_embedding(invalid)


@pytest.mark.asyncio
async def test_embedding_reaches_native_sdk_with_documented_shape() -> None:
    requests: list[dict[str,object]] = []
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert request.url.path.endswith("gemini-embedding-2:batchEmbedContents")
        return httpx.Response(200,json={"embeddings":[{"values":[3,4]+[0]*766}]})
    client = genai.Client(api_key="fixture-key",http_options=HttpOptions(
        async_client_args={"transport":httpx.MockTransport(respond)}))
    try:
        embedding = await GeminiEmbeddingClient(client.aio).embed_text("task: search result | query: What works?")
        assert embedding[:2] == [0.6,0.8]
        assert requests == [{"requests":[{"model":"models/gemini-embedding-2","content":{"parts":[{"text":"task: search result | query: What works?"}]},"outputDimensionality":768}]}]
    finally:
        await client.aio.aclose()
        client.close()


@pytest.mark.asyncio
async def test_embedding_oversized_text_is_not_silently_truncated() -> None:
    requests: list[httpx.Request] = []
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)
    client = genai.Client(api_key="fixture-key",http_options=HttpOptions(async_client_args={"transport":httpx.MockTransport(respond)}))
    try:
        with pytest.raises(ProviderError) as error:
            await GeminiEmbeddingClient(client.aio).embed_text("a"*8193)
        assert error.value.code == "embedding_context_limit"
        assert not requests
    finally:
        await client.aio.aclose()
        client.close()


@pytest.mark.asyncio
async def test_missing_sdk_client_fails_instead_of_returning_a_vector() -> None:
    with pytest.raises(ProviderError) as error:
        await GeminiEmbeddingClient(None).embed_text("task: search result | query: Anything")
    assert error.value.code == "embedding_not_configured"


def test_query_and_document_text_match_the_documented_profile() -> None:
    assert query_text("What works?") == "task: search result | query: What works?"
    assert document_text("Title", "Abstract") == "title: Title | text: Abstract"
