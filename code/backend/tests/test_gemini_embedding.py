"""Tests for Gemini Embedding Provider and PaperEmbeddingService."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider, GeminiService
from features.embedding.service import PaperEmbeddingService


# ==============================================================================
# SECTION 1: ASYMMETRIC PROMPT FORMATTING & INITIALIZATION
# ==============================================================================

def test_gemini_provider_format_document_with_title() -> None:
    """Test asymmetric document format with a valid title."""
    formatted = GeminiEmbeddingProvider._format_document(
        text="Graph algorithms accelerate scientific literature discovery.",
        title="GraphSelect Discovery Engine",
    )
    assert formatted == "title: GraphSelect Discovery Engine | text: Graph algorithms accelerate scientific literature discovery."


def test_gemini_provider_format_document_without_title() -> None:
    """Test asymmetric document format defaults to title: none when title is omitted or empty."""
    formatted_none = GeminiEmbeddingProvider._format_document(
        text="Sample abstract without title.",
        title=None,
    )
    assert formatted_none == "title: none | text: Sample abstract without title."

    formatted_empty = GeminiEmbeddingProvider._format_document(
        text="Sample abstract with empty title.",
        title="",
    )
    assert formatted_empty == "title: none | text: Sample abstract with empty title."


def test_gemini_provider_format_query() -> None:
    """Test asymmetric query format with task prefix."""
    formatted = GeminiEmbeddingProvider._format_query(
        query="What are the main graph neural network architectures?",
        task="question answering",
    )
    assert formatted == "task: question answering | query: What are the main graph neural network architectures?"


def test_gemini_provider_initialization_modes() -> None:
    """Test Gemini provider initialization in Vertex AI mode vs Google AI Studio mode."""
    # Test Google AI Studio mode
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "studio_key_abc"
        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client:
            provider = GeminiEmbeddingProvider(output_dimensionality=768)
            mock_client.assert_called_once_with(api_key="studio_key_abc", vertexai=False)
            assert provider.model_name == "gemini-embedding-2"
            assert provider.dimensions == 768

    # Test Vertex AI mode
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = True
        mock_settings.return_value.vertex_project = "my-gcp-project"
        mock_settings.return_value.vertex_location = "us-central1"
        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client:
            provider = GeminiEmbeddingProvider(output_dimensionality=768)
            mock_client.assert_called_once_with(
                vertexai=True,
                project="my-gcp-project",
                location="us-central1",
            )


# ==============================================================================
# SECTION 2: VECTOR GENERATION & RETRY ON 429
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_embed_document_and_query_success() -> None:
    """Test embed_document and embed_query generate expected dimensionality vectors."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"
        
        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_embedding = MagicMock()
            mock_embedding.values = [0.05] * 768
            mock_result = MagicMock()
            mock_result.embeddings = [mock_embedding]
            mock_client.models.embed_content.return_value = mock_result

            provider = GeminiEmbeddingProvider(api_key="dummy_key", output_dimensionality=768)

            doc_vec = await provider.embed_document(
                text="This is a test abstract.",
                title="Test Title",
                session_id="session-1",
            )
            assert len(doc_vec) == 768
            assert doc_vec[0] == 0.05

            query_vec = await provider.embed_query(
                query="What is graph discovery?",
                session_id="session-1",
            )
            assert len(query_vec) == 768
            assert query_vec[0] == 0.05

            # Test embed_paper alias
            alias_vec = await provider.embed_paper(
                text="This is a test abstract.",
                title="Test Title",
            )
            assert len(alias_vec) == 768


@pytest.mark.asyncio
async def test_gemini_embed_handles_429_retry() -> None:
    """Test Gemini provider exponential backoff on HTTP 429."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value

            class Mock429Error(Exception):
                code = 429

            mock_embedding = MagicMock()
            mock_embedding.values = [0.1] * 768
            mock_success = MagicMock()
            mock_success.embeddings = [mock_embedding]

            mock_client.models.embed_content.side_effect = [Mock429Error("Quota exceeded"), mock_success]

            provider = GeminiEmbeddingProvider(api_key="dummy_key")

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                vec = await provider.embed_document("Text abstract", title="Title")
                assert len(vec) == 768
                assert mock_sleep.call_count == 1
                assert mock_client.models.embed_content.call_count == 2


# ==============================================================================
# SECTION 3: PAPER EMBEDDING SERVICE ORCHESTRATION
# ==============================================================================

@pytest.mark.asyncio
async def test_paper_embedding_service_passes_title_to_provider() -> None:
    """Test PaperEmbeddingService fetches title from Neo4j and passes it to embed_document."""
    mock_neo4j = AsyncMock()
    mock_neo4j.has_embedding.return_value = False
    mock_neo4j.get_paper_by_doi.return_value = {
        "doi": "10.1000/graphselect",
        "title": "GraphSelect: Citation-Aware Search",
        "abstract": "We present GraphSelect, a graph-based literature retrieval engine.",
    }
    mock_neo4j.store_paper_embedding.return_value = None

    mock_provider = AsyncMock()
    mock_provider.model_name = "gemini-embedding-2"
    mock_provider.embed_document.return_value = [0.2] * 768

    service = PaperEmbeddingService(
        neo4j=mock_neo4j,
        provider=mock_provider,
    )

    result = await service.embed_paper("10.1000/graphselect", session_id="session-99")

    assert result is True
    mock_neo4j.has_embedding.assert_called_once_with("10.1000/graphselect")
    mock_neo4j.get_paper_by_doi.assert_called_once_with("10.1000/graphselect")
    
    # Crucial assertion: provider.embed_document MUST receive abstract and title
    mock_provider.embed_document.assert_called_once_with(
        "We present GraphSelect, a graph-based literature retrieval engine.",
        title="GraphSelect: Citation-Aware Search",
        session_id="session-99",
    )

    mock_neo4j.store_paper_embedding.assert_called_once_with(
        "10.1000/graphselect",
        [0.2] * 768,
        model="gemini-embedding-2",
    )


@pytest.mark.asyncio
async def test_paper_embedding_service_skips_when_already_embedded_or_no_abstract() -> None:
    """Test PaperEmbeddingService skips papers that already have embedding or lack abstract."""
    mock_neo4j = AsyncMock()
    mock_provider = AsyncMock()
    service = PaperEmbeddingService(neo4j=mock_neo4j, provider=mock_provider)

    # 1. Already has embedding
    mock_neo4j.has_embedding.return_value = True
    assert await service.embed_paper("10.1000/done") is False
    mock_provider.embed_document.assert_not_called()

    # 2. No abstract in paper node
    mock_neo4j.has_embedding.return_value = False
    mock_neo4j.get_paper_by_doi.return_value = {"doi": "10.1000/no_abstract", "title": "No Abstract Paper", "abstract": None}
    assert await service.embed_paper("10.1000/no_abstract") is False
    mock_provider.embed_document.assert_not_called()


@pytest.mark.asyncio
async def test_paper_embedding_service_embed_questions() -> None:
    """Test PaperEmbeddingService embeds list of research questions and persists them in Neo4j."""
    mock_neo4j = AsyncMock()
    mock_neo4j.store_question_embedding.return_value = None

    mock_provider = AsyncMock()
    mock_provider.model_name = "gemini-embedding-2"
    mock_provider.embed_query.return_value = [0.3] * 768

    service = PaperEmbeddingService(
        neo4j=mock_neo4j,
        provider=mock_provider,
    )

    questions = [
        "What are graph neural networks?",
        "How does citation analysis improve retrieval?",
    ]

    await service.embed_questions("session-42", questions)

    assert mock_provider.embed_query.call_count == 2
    assert mock_neo4j.store_question_embedding.call_count == 2
    mock_neo4j.store_question_embedding.assert_any_call(
        session_id="session-42",
        question_text="What are graph neural networks?",
        embedding=[0.3] * 768,
        model="gemini-embedding-2",
    )


# ==============================================================================
# SECTION 4: BATCH EMBEDDING CAPABILITIES
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_provider_batch_embed_documents_success() -> None:
    """Test batch_embed_documents issues a single API call for multiple documents."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_emb1 = MagicMock()
            mock_emb1.values = [0.1] * 768
            mock_emb2 = MagicMock()
            mock_emb2.values = [0.2] * 768

            mock_result = MagicMock()
            mock_result.embeddings = [mock_emb1, mock_emb2]
            mock_client.models.embed_content.return_value = mock_result

            provider = GeminiEmbeddingProvider(api_key="dummy_key", output_dimensionality=768)

            docs = [
                ("Abstract 1", "Title 1"),
                ("Abstract 2", "Title 2"),
            ]
            vectors = await provider.batch_embed_documents(docs, session_id="sess-batch")

            assert len(vectors) == 2
            assert vectors[0] == [0.1] * 768
            assert vectors[1] == [0.2] * 768

            # Exactly 1 single embed_content call for both documents
            assert mock_client.models.embed_content.call_count == 1
            call_kwargs = mock_client.models.embed_content.call_args.kwargs
            assert call_kwargs["contents"] == [
                "title: Title 1 | text: Abstract 1",
                "title: Title 2 | text: Abstract 2",
            ]


@pytest.mark.asyncio
async def test_gemini_provider_batch_embed_documents_chunking() -> None:
    """Test batch_embed_documents chunks requests according to batch_size."""
    with patch("config.get_settings") as mock_settings:
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = "dummy_key"

        with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value

            def make_mock_result(*args, **kwargs):
                contents = kwargs.get("contents", [])
                res = MagicMock()
                res.embeddings = [MagicMock(values=[0.5] * 768) for _ in contents]
                return res

            mock_client.models.embed_content.side_effect = make_mock_result

            provider = GeminiEmbeddingProvider(api_key="dummy_key", output_dimensionality=768)

            docs = [(f"Abstract {i}", f"Title {i}") for i in range(5)]
            vectors = await provider.batch_embed_documents(docs, batch_size=2)

            assert len(vectors) == 5
            # 5 items with batch_size=2 -> ceil(5/2) = 3 calls
            assert mock_client.models.embed_content.call_count == 3


@pytest.mark.asyncio
async def test_gemini_provider_without_credentials_raises_runtime_error() -> None:
    """Test that attempting to embed without credentials immediately raises RuntimeError."""
    with patch("config.get_settings") as mock_settings, patch.dict(
        "os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}
    ):
        mock_settings.return_value.use_vertex_ai = False
        mock_settings.return_value.gemini_api_key = ""

        provider = GeminiEmbeddingProvider(api_key="", output_dimensionality=768)
        assert provider._client is None

        docs = [("Unauthenticated text 1", "T1"), ("Unauthenticated text 2", "T2")]
        with pytest.raises(RuntimeError, match="Gemini API client is not initialized"):
            await provider.batch_embed_documents(docs)

        with pytest.raises(RuntimeError, match="Gemini API client is not initialized"):
            await provider.embed_document("Unauthenticated text", title="T")

        with pytest.raises(RuntimeError, match="Gemini API client is not initialized"):
            await provider.embed_query("Unauthenticated query")
