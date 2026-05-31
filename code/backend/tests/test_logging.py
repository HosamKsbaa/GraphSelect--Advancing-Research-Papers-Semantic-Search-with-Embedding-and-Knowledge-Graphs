"""Tests for LogService structured logging, timezone conversions, and fallback warnings."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.logging.log_service import LogService


@pytest.mark.asyncio
async def test_log_service_successful_app_log() -> None:
    """Test standard structured application log insertion in MySQL."""
    mock_mysql = AsyncMock()
    log_service = LogService(mock_mysql)

    await log_service.log(
        level="INFO",
        module="test_module",
        message="A test message",
        session_id="session-xyz",
        extra={"meta": "data"},
    )

    mock_mysql.execute.assert_called_once()
    query = mock_mysql.execute.call_args[0][0]
    args = mock_mysql.execute.call_args[0][1]

    assert "INSERT INTO app_logs" in query
    assert args == ("session-xyz", "INFO", "test_module", "A test message", '{"meta": "data"}')


@pytest.mark.asyncio
async def test_log_service_app_log_fallback_on_error() -> None:
    """Test that standard Python logging warning acts as fallback when MySQL write fails."""
    mock_mysql = AsyncMock()
    mock_mysql.execute.side_effect = Exception("MySQL connectivity lost")
    log_service = LogService(mock_mysql)

    # Use patch to verify that logger.warning is called with custom fallback pattern
    with patch("core.logging.log_service.logger.warning") as mock_warn:
        await log_service.log(
            level="ERROR",
            module="crawlers",
            message="Lost Neo4j connection",
            session_id="session-xyz",
            extra={"details": "port 7687 closed"},
        )
        mock_warn.assert_called_once()
        warning_args = mock_warn.call_args[0][0]
        assert "[FALLBACK APP LOG]" in warning_args


@pytest.mark.asyncio
async def test_log_service_app_log_non_serializable_extra() -> None:
    """Test that application log succeeds even when extra contains non-serializable objects."""
    mock_mysql = AsyncMock()
    log_service = LogService(mock_mysql)

    class CustomObject:
        def __str__(self) -> str:
            return "custom_str"

    await log_service.log(
        level="INFO",
        module="test_module",
        message="A test message",
        session_id="session-xyz",
        extra={"error_obj": ValueError("some exception"), "custom_obj": CustomObject()},
    )

    mock_mysql.execute.assert_called_once()
    args = mock_mysql.execute.call_args[0][1]
    import json
    parsed_extra = json.loads(args[4])
    assert parsed_extra["error_obj"] == "some exception"
    assert parsed_extra["custom_obj"] == "custom_str"


@pytest.mark.asyncio
async def test_log_service_successful_api_log() -> None:
    """Test standard API request log insertion in MySQL."""
    mock_mysql = AsyncMock()
    log_service = LogService(mock_mysql)

    await log_service.log_api_request(
        service="OpenAlex",
        method="GET",
        url="https://api.openalex.org/works",
        status_code=200,
        response_time_ms=150,
        payload_summary="Successful fetch",
        session_id="session-123",
    )

    mock_mysql.execute.assert_called_once()
    query = mock_mysql.execute.call_args[0][0]
    args = mock_mysql.execute.call_args[0][1]

    assert "INSERT INTO api_logs" in query
    assert args == ("session-123", "OpenAlex", "GET", "https://api.openalex.org/works", 200, 150, "Successful fetch", None, None)


@pytest.mark.asyncio
async def test_log_service_api_log_fallback_on_error() -> None:
    """Test standard Python logging acts as fallback when MySQL API logs write fails."""
    mock_mysql = AsyncMock()
    mock_mysql.execute.side_effect = Exception("MySQL connection pool exhausted")
    log_service = LogService(mock_mysql)

    with patch("core.logging.log_service.logger.warning") as mock_warn:
        await log_service.log_api_request(
            service="Gemini",
            method="POST",
            url="https://generativelanguage.googleapis.com",
            status_code=500,
            response_time_ms=2300,
            payload_summary="Internal Error",
            session_id="session-123",
        )
        mock_warn.assert_called_once()
        warning_args = mock_warn.call_args[0][0]
        assert "[FALLBACK API LOG]" in warning_args


@pytest.mark.asyncio
async def test_log_service_get_app_logs_timezone_conversion() -> None:
    """Test that timezone-aware datetime query filters are properly converted to UTC naive string."""
    mock_mysql = AsyncMock()
    mock_mysql.fetch_all.return_value = []
    log_service = LogService(mock_mysql)

    # Test UTC timezone aware
    since_utc = datetime(2026, 5, 30, 16, 24, 0, tzinfo=timezone.utc)
    await log_service.get_app_logs(since=since_utc)

    mock_mysql.fetch_all.assert_called_once()
    args = mock_mysql.fetch_all.call_args[0][1]
    assert "2026-05-30 16:24:00" in args

    # Reset mock and test local timezone offset (+02:00, representing 18:24:00 local time)
    mock_mysql.reset_mock()
    from datetime import timedelta
    local_tz = timezone(timedelta(hours=2))
    since_local = datetime(2026, 5, 30, 18, 24, 0, tzinfo=local_tz)

    await log_service.get_app_logs(since=since_local)
    mock_mysql.fetch_all.assert_called_once()
    args_local = mock_mysql.fetch_all.call_args[0][1]
    # Local 18:24:00+02:00 converts to UTC 16:24:00
    assert "2026-05-30 16:24:00" in args_local


@pytest.mark.asyncio
async def test_gemini_service_exception_logging() -> None:
    """Test that GeminiEmbeddingProvider logs to log_service even when the API throws an exception."""
    from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
    
    mock_log_service = AsyncMock()
    # Mock Gemini client
    with patch("features.embedding.providers.gemini_provider.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        # Make embed_content raise an exception
        mock_client.models.embed_content.side_effect = Exception("Invalid API key")
        
        service = GeminiEmbeddingProvider(
            api_key="bad-key",
            log_service=mock_log_service,
        )
        
        with pytest.raises(Exception, match="Invalid API key"):
            await service.embed_document("Some paper abstract", session_id="session-456")
            
        mock_log_service.log_api_request.assert_called_once()
        call_kwargs = mock_log_service.log_api_request.call_args[1]
        assert call_kwargs["service"] == "Gemini"
        assert call_kwargs["status_code"] == 500
        assert "FAILED" in call_kwargs["payload_summary"]
        assert call_kwargs["session_id"] == "session-456"


@pytest.mark.asyncio
async def test_openalex_service_exception_logging() -> None:
    """Test that OpenAlexService logs to log_service even when the HTTP request throws an exception."""
    from core.clients.openalex_client import OpenAlexService
    import httpx
    
    mock_log_service = AsyncMock()
    
    # We want to mock httpx.AsyncClient.request to raise a ConnectError
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_request.side_effect = httpx.ConnectError("Connection refused")
        
        service = OpenAlexService(
            api_key="",
            log_service=mock_log_service,
        )
        
        with pytest.raises(httpx.ConnectError):
            await service.get_paper_by_doi("10.1234/nonexistent", session_id="session-789")
            
        mock_log_service.log_api_request.assert_called_once()
        call_kwargs = mock_log_service.log_api_request.call_args[1]
        assert call_kwargs["service"] == "OpenAlex"
        assert call_kwargs["status_code"] == 500
        assert "FAILED" in call_kwargs["payload_summary"]
        assert call_kwargs["session_id"] == "session-789"


@pytest.mark.asyncio
async def test_log_service_api_log_service_canonicalization() -> None:
    """Test that log_api_request and get_api_logs canonicalize service names."""
    mock_mysql = AsyncMock()
    log_service = LogService(mock_mysql)

    # 1. Test insertion canonicalization
    await log_service.log_api_request(
        service="openalex",
        method="GET",
        url="https://api.openalex.org",
        session_id="session-1",
    )
    mock_mysql.execute.assert_called_once()
    args = mock_mysql.execute.call_args[0][1]
    assert args[1] == "OpenAlex"  # Stored as uniform "OpenAlex"

    mock_mysql.reset_mock()
    await log_service.log_api_request(
        service="gemini",
        method="POST",
        url="https://api.gemini.org",
        session_id="session-2",
    )
    mock_mysql.execute.assert_called_once()
    args = mock_mysql.execute.call_args[0][1]
    assert args[1] == "Gemini"  # Stored as uniform "Gemini"

    # 2. Test querying canonicalization (database query is case-insensitive LOWER matching)
    mock_mysql.reset_mock()
    mock_mysql.fetch_all.return_value = []
    await log_service.get_api_logs(service="openalex")
    mock_mysql.fetch_all.assert_called_once()
    query_args = mock_mysql.fetch_all.call_args[0][1]
    assert "openalex" in query_args

    mock_mysql.reset_mock()
    await log_service.get_api_logs(service="gemini")
    mock_mysql.fetch_all.assert_called_once()
    query_args = mock_mysql.fetch_all.call_args[0][1]
    assert "gemini" in query_args


@pytest.mark.asyncio
async def test_log_service_write_and_retrieve_with_datetime() -> None:
    """Test standard write and retrieval sequence based on date/time bounds."""
    mock_mysql = AsyncMock()
    
    # Mock data to return from fetch_all
    mock_records = [
        {
            "id": 1,
            "session_id": "session-datetime-test",
            "service": "Gemini",
            "method": "POST",
            "url": "models/text-embedding-005:embedContent",
            "status_code": 200,
            "response_time_ms": 250,
            "payload_summary": "Embedded text",
            "created_at": datetime(2026, 5, 30, 17, 30, 0),
        }
    ]
    mock_mysql.fetch_all.return_value = mock_records
    log_service = LogService(mock_mysql)

    # 1. Log an API request
    await log_service.log_api_request(
        service="Gemini",
        method="POST",
        url="models/text-embedding-005:embedContent",
        status_code=200,
        response_time_ms=250,
        payload_summary="Embedded text",
        session_id="session-datetime-test",
    )
    
    mock_mysql.execute.assert_called_once()
    insert_args = mock_mysql.execute.call_args[0][1]
    assert insert_args[0] == "session-datetime-test"
    assert insert_args[1] == "Gemini"

    # 2. Query logs based on date time (using a since filter)
    since_filter = datetime(2026, 5, 30, 17, 0, 0, tzinfo=timezone.utc)
    results = await log_service.get_api_logs(
        session_id="session-datetime-test",
        since=since_filter,
    )

    mock_mysql.fetch_all.assert_called_once()
    query_string = mock_mysql.fetch_all.call_args[0][0]
    query_args = mock_mysql.fetch_all.call_args[0][1]

    # Verify that the since filter was correctly parsed to UTC and formatted
    assert "created_at >= %s" in query_string
    assert "2026-05-30 17:00:00" in query_args
    assert len(results) == 1
    assert results[0]["session_id"] == "session-datetime-test"
    assert results[0]["service"] == "Gemini"


@pytest.mark.asyncio
async def test_log_service_get_app_logs_since_filtering() -> None:
    """Test that timezone-naive datetime query filters are properly formatted as naive strings for MySQL."""
    mock_mysql = AsyncMock()
    mock_mysql.fetch_all.return_value = []
    log_service = LogService(mock_mysql)

    # Timezone-naive datetime
    since_naive = datetime(2026, 5, 30, 19, 20, 0)
    await log_service.get_app_logs(since=since_naive)

    mock_mysql.fetch_all.assert_called_once()
    args = mock_mysql.fetch_all.call_args[0][1]
    assert "2026-05-30 19:20:00" in args
    query = mock_mysql.fetch_all.call_args[0][0]
    assert "created_at >= %s" in query


@pytest.mark.asyncio
async def test_log_service_get_api_logs_timezone_aware_since_filtering() -> None:
    """Test that timezone-aware datetime query filters for API logs are correctly converted to UTC naive format."""
    mock_mysql = AsyncMock()
    mock_mysql.fetch_all.return_value = []
    log_service = LogService(mock_mysql)

    # Local timezone offset (+02:00, representing 19:20:00 local time)
    from datetime import timedelta
    local_tz = timezone(timedelta(hours=2))
    since_local = datetime(2026, 5, 30, 19, 20, 0, tzinfo=local_tz)

    await log_service.get_api_logs(since=since_local)

    mock_mysql.fetch_all.assert_called_once()
    args = mock_mysql.fetch_all.call_args[0][1]
    # Local 19:20:00+02:00 converts to UTC 17:20:00 naive string
    assert "2026-05-30 17:20:00" in args
    query = mock_mysql.fetch_all.call_args[0][0]
    assert "created_at >= %s" in query


def test_openalex_abstract_reconstruction() -> None:
    """Test that OpenAlexService reconstructs plain text from abstract_inverted_index correctly."""
    from core.clients.openalex_client import OpenAlexService

    # 1. Valid index
    index = {
        "The": [0],
        "system": [1, 5],
        "works": [2],
        "extremely": [3],
        "well.": [4],
        "This": [6],
        "system!": [7]
    }
    reconstructed = OpenAlexService._reconstruct_abstract(index)
    assert reconstructed == "The system works extremely well. system This system!"

    # 2. None / Empty inputs
    assert OpenAlexService._reconstruct_abstract(None) is None
    assert OpenAlexService._reconstruct_abstract({}) is None
    assert OpenAlexService._reconstruct_abstract("not a dict") is None  # type: ignore[arg-type]

