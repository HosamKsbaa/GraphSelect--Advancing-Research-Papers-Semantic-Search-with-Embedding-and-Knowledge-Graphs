"""Adversarial stress and fuzz test suite for Settings and Dual-Mode Auth endpoints.

This module empirically challenges:
1. Payload Fuzzing:
   - Empty strings, whitespace, nulls, long strings (100KB-1MB), Unicode/emojis.
   - Injection payloads: SQLi, XSS, CRLF newline injection, quote escaping.
   - Type corruption: integers, booleans, arrays, dicts, invalid enum literals.
2. Concurrency & Stress:
   - High-concurrency simultaneous .env writes (PUT /api/settings, POST /api/settings/auth) via AsyncClient.
   - Interleaved concurrent reads and writes verifying atomic file writes and zero corruption.
3. Non-Destructive Probing:
   - POST /api/settings/test-connection isolation (guaranteeing .env is unmodified).
   - In-memory runtime settings immunity to test-connection candidate credentials.
4. Hot-Swapping & Fault Tolerance:
   - Rapid back-and-forth mode toggling (Studio <-> Vertex).
   - Fault tolerance when ServiceRegistry attributes are absent or uninitialized.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
import httpx
from httpx import ASGITransport

from config import get_settings
from core.llm.service import LLMService
import features.settings.router as settings_router_module
from features.settings.router import (
    _clean_key_value,
    _get_env_value,
    _is_real_key,
    _is_real_project,
    _mask_key,
    _read_env_lines,
    _set_env_line,
    _update_env_file,
    reload_runtime_services,
    sync_os_environ_from_env,
)
from features.settings.models import (
    AuthUpdateRequest,
    SettingsUpdateRequest,
    TestConnectionRequest as ConnectionRequestModel,
)
from main import app


@pytest.fixture
def isolated_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture providing an isolated temporary .env file for adversarial testing."""
    env_content = (
        "# Base Test Environment\n"
        "GEMINI_API_KEY=AIzaSyOriginalProdKey12345678\n"
        "USE_VERTEX_AI=false\n"
        "VERTEX_PROJECT=original-prod-gcp-project\n"
        "VERTEX_LOCATION=us-central1\n"
        "OPENALEX_API_KEY=openalex-orig-key-1111\n"
        "OPENALEX_EMAIL=admin@institution.edu\n"
        "NEO4J_PASSWORD=original-neo4j-secret\n"
        "MYSQL_PASSWORD=original-mysql-secret\n"
    )
    test_env = tmp_path / ".env"
    test_env.write_text(env_content, encoding="utf-8")
    monkeypatch.setattr(settings_router_module, "ENV_FILE", test_env)
    return test_env


# ==============================================================================
# SECTION 1: PAYLOAD FUZZING (BOUNDARY, INJECTION, AND TYPE STRESS)
# ==============================================================================

@pytest.mark.parametrize("fuzz_value", [
    "",
    "   ",
    "\t",
    "\n",
    "\r\n",
    "   \n  \t  ",
])
def test_fuzz_whitespace_and_empty_payloads(isolated_env_file: Path, fuzz_value: str) -> None:
    """Verify that whitespace-only and empty strings are handled gracefully without corruption."""
    client = TestClient(app)

    # 1. Update auth with whitespace
    payload = {
        "gemini_api_key": fuzz_value,
        "vertex_project": fuzz_value,
        "openalex_email": fuzz_value,
    }
    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Whitespace should be stripped to empty string
        assert data["gemini_api_key_set"] is False
        assert data["gemini_api_key_preview"] == "Not set"
        assert data["has_credentials"] is False

    # Verify .env does not contain malformed whitespace lines
    lines = isolated_env_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith("GEMINI_API_KEY="):
            assert line == "GEMINI_API_KEY="
        if line.startswith("VERTEX_PROJECT="):
            assert line == "VERTEX_PROJECT="


def test_fuzz_massive_string_payload(isolated_env_file: Path) -> None:
    """Stress test with 100KB+ massive payload string to test buffer and parser resilience."""
    client = TestClient(app)
    massive_key = "AIzaSy" + ("X" * 100_000)

    payload = {
        "mode": "studio",
        "gemini_api_key": massive_key,
    }
    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["gemini_api_key_set"] is True
        assert data["gemini_api_key_preview"].endswith("XXXX")
        # Masking should not allocate 100k bullets; max 20 bullets + last 4 chars
        assert len(data["gemini_api_key_preview"]) <= 30


@pytest.mark.parametrize("injection_payload", [
    # CRLF / Newline Injection
    "AIzaSyKey\r\nMALICIOUS_VAR=injected_val\r\n",
    "AIzaSyKey\nINJECTED_KEY=compromised\n",
    # SQLi strings
    "' OR '1'='1' --",
    "admin'/*",
    # XSS payloads
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert(1)>",
    # Shell / special characters
    "; rm -rf / ;",
    "$(whoami)",
    "`id`",
    "key with spaces and # comments and = equals",
    "key'\"with`quotes`",
    # Unicode and Emojis
    "🔑⚡🧪🧬🤖—中文—العربية—русский—日本語",
])
def test_fuzz_injection_and_special_character_payloads(
    isolated_env_file: Path, injection_payload: str
) -> None:
    """Verify adversarial payloads (CRLF, XSS, SQLi, shell chars, unicode) are stored safely."""
    client = TestClient(app)

    payload = {
        "mode": "studio",
        "gemini_api_key": injection_payload,
        "openalex_email": "test+injection@domain.com",
    }
    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mode"] == "studio"

    # Verify .env lines are intact and no arbitrary variables were injected
    env_text = isolated_env_file.read_text(encoding="utf-8")
    assert "MALICIOUS_VAR=" not in env_text
    assert "INJECTED_KEY=" not in env_text


@pytest.mark.parametrize("invalid_payload, expected_status", [
    ({"mode": "invalid_mode_name"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"mode": 12345}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"mode": ["studio"]}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"use_vertex_ai": "not_a_boolean"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"gemini_api_key": 123456789}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"gemini_api_key": ["array_of_keys"]}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ({"vertex_project": {"nested": "object"}}, status.HTTP_422_UNPROCESSABLE_ENTITY),
])
def test_fuzz_schema_and_type_validation(
    isolated_env_file: Path, invalid_payload: dict, expected_status: int
) -> None:
    """Verify Pydantic models reject invalid data types and enums with HTTP 422."""
    client = TestClient(app)
    response = client.post("/api/settings/auth", json=invalid_payload)
    assert response.status_code == expected_status


def test_fuzz_extra_unexpected_fields(isolated_env_file: Path) -> None:
    """Verify unexpected fields in request body are ignored without crash."""
    client = TestClient(app)
    payload = {
        "mode": "studio",
        "gemini_api_key": "AIzaSyValidWithExtraField",
        "unexpected_extra_field": "attacker_payload",
        "admin_role": True,
        "root_password": "pwned",
    }
    with patch("core.llm.service.genai.Client"):
        response = client.post("/api/settings/auth", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mode"] == "studio"
        assert "unexpected_extra_field" not in data


# ==============================================================================
# SECTION 2: ASYNC CONCURRENCY & RACE CONDITION STRESS TESTING
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_async_env_updates_under_heavy_load(isolated_env_file: Path) -> None:
    """Stress test concurrent updates to .env using 30 simultaneous async tasks."""
    transport = ASGITransport(app=app)
    num_tasks = 30
    keys_written = [f"AIzaSyConcurrentTestKey_{i:04d}" for i in range(num_tasks)]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def worker_update(idx: int):
            payload = {
                "mode": "studio",
                "gemini_api_key": keys_written[idx],
                "vertex_project": f"gcp-project-{idx}",
                "openalex_email": f"worker_{idx}@lab.org",
            }
            with patch("core.llm.service.genai.Client"):
                resp = await client.post("/api/settings/auth", json=payload)
                return resp.status_code

        results = await asyncio.gather(*[worker_update(i) for i in range(num_tasks)])

    # All requests should return 200 OK without race condition errors
    assert all(code == status.HTTP_200_OK for code in results)

    # Verify .env file is not corrupted
    lines = isolated_env_file.read_text(encoding="utf-8").splitlines()
    key_lines = [l for l in lines if l.startswith("GEMINI_API_KEY=")]
    project_lines = [l for l in lines if l.startswith("VERTEX_PROJECT=")]
    email_lines = [l for l in lines if l.startswith("OPENALEX_EMAIL=")]

    # Exactly 1 entry for each key should exist (no duplicate corrupted lines)
    assert len(key_lines) == 1
    assert len(project_lines) == 1
    assert len(email_lines) == 1

    # Verify the file can be cleanly read by GET /api/settings/auth
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        get_resp = await client.get("/api/settings/auth")
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["has_credentials"] is True


@pytest.mark.asyncio
async def test_concurrent_interleaved_async_reads_and_writes(isolated_env_file: Path) -> None:
    """Test concurrent async reads and writes ensuring reads never encounter partial writes."""
    transport = ASGITransport(app=app)
    read_statuses = []
    write_statuses = []

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def reader_worker():
            for _ in range(15):
                r1 = await client.get("/api/settings/auth")
                r2 = await client.get("/api/settings")
                read_statuses.append((r1.status_code, r2.status_code))
                await asyncio.sleep(0.005)

        async def writer_worker(worker_id: int):
            for i in range(5):
                payload = {
                    "mode": "vertex" if (i % 2 == 0) else "studio",
                    "gemini_api_key": f"AIzaSyInterleavedKey_{worker_id}_{i}",
                    "vertex_project": f"project-interleaved-{worker_id}-{i}",
                }
                with patch("core.llm.service.genai.Client"):
                    r = await client.post("/api/settings/auth", json=payload)
                    write_statuses.append(r.status_code)
                await asyncio.sleep(0.005)

        readers = [reader_worker() for _ in range(5)]
        writers = [writer_worker(i) for i in range(5)]
        await asyncio.gather(*readers, *writers)

    # All reads and writes must succeed with 200 OK
    assert all(w == status.HTTP_200_OK for w in write_statuses)
    assert all(r1 == status.HTTP_200_OK and r2 == status.HTTP_200_OK for r1, r2 in read_statuses)


# ==============================================================================
# SECTION 3: NON-DESTRUCTIVE CONNECTION TESTER VERIFICATION
# ==============================================================================

def test_connection_test_does_not_mutate_env_or_runtime_state(isolated_env_file: Path) -> None:
    """Empirically verify that test-connection is completely non-destructive."""
    initial_env = isolated_env_file.read_text(encoding="utf-8")
    client = TestClient(app)

    # 1. Test connection with valid Studio candidate key
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "pong"
        mock_client.models.generate_content.return_value = mock_resp

        probe_payload = {
            "mode": "studio",
            "gemini_api_key": "AIzaSyCandidateProbeKey9999",
        }
        res = client.post("/api/settings/test-connection", json=probe_payload)
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["success"] is True

    # 2. Test connection with failing Vertex AI candidate project
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception("PermissionDenied: 403 Forbidden")

        probe_payload = {
            "mode": "vertex",
            "vertex_project": "candidate-nonexistent-project",
            "vertex_location": "us-west1",
        }
        res = client.post("/api/settings/test-connection", json=probe_payload)
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["success"] is False

    # 3. CRITICAL CHECK: Ensure .env file on disk is bit-for-bit identical
    current_env = isolated_env_file.read_text(encoding="utf-8")
    assert current_env == initial_env

    # 4. CRITICAL CHECK: Ensure GET /api/settings/auth still reflects original configuration
    auth_status = client.get("/api/settings/auth").json()
    assert auth_status["mode"] == "studio"
    assert auth_status["gemini_api_key_preview"].endswith("5678")
    assert auth_status["vertex_project"] == "original-prod-gcp-project"


def test_connection_test_with_empty_and_default_fallbacks(isolated_env_file: Path) -> None:
    """Test POST /api/settings/test-connection falls back to existing env when fields omitted."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "pong"
        mock_client.models.generate_content.return_value = mock_resp

        # Empty body -> should fall back to configured settings
        res = client.post("/api/settings/test-connection", json={})
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["success"] is True


# ==============================================================================
# SECTION 4: HOT-SWAPPING & FAULT TOLERANCE STRESS
# ==============================================================================

def test_rapid_mode_switching_cycle(isolated_env_file: Path) -> None:
    """Stress test rapidly alternating between Studio and Vertex modes 10 times."""
    client = TestClient(app)

    for iteration in range(10):
        # Switch to Vertex
        vertex_payload = {
            "mode": "vertex",
            "vertex_project": f"iter-gcp-proj-{iteration}",
            "vertex_location": "europe-west1",
        }
        with patch("core.llm.service.genai.Client"):
            resp = client.post("/api/settings/auth", json=vertex_payload)
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["mode"] == "vertex"
            assert data["use_vertex_ai"] is True
            assert data["vertex_project"] == f"iter-gcp-proj-{iteration}"

        # Switch to Studio
        studio_payload = {
            "mode": "studio",
            "gemini_api_key": f"AIzaSyIterStudioKey_{iteration:02d}",
        }
        with patch("core.llm.service.genai.Client"):
            resp = client.post("/api/settings/auth", json=studio_payload)
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["mode"] == "studio"
            assert data["use_vertex_ai"] is False
            assert data["gemini_api_key_preview"].endswith(f"{iteration:02d}")


def test_reload_runtime_services_fault_tolerance(isolated_env_file: Path) -> None:
    """Test reload_runtime_services when ServiceRegistry has missing or corrupted attributes."""
    from agents._service_registry import ServiceRegistry

    # Temporarily set missing/None attributes on ServiceRegistry
    original_initialized = getattr(ServiceRegistry, "_initialized", False)
    ServiceRegistry._initialized = True
    ServiceRegistry._planning_service = None
    ServiceRegistry._writing_service = None
    ServiceRegistry._paper_retrieval = None

    try:
        # Should execute cleanly without throwing AttributeError or crashing
        llm, embedding = reload_runtime_services(app_state=None)
        assert llm is not None
        assert embedding is not None
    finally:
        ServiceRegistry._initialized = original_initialized


# ==============================================================================
# SECTION 5: HELPER FUNCTION ADVERSARIAL EDGE CASES
# ==============================================================================

def test_mask_key_extreme_edge_cases() -> None:
    """Test _mask_key with various edge cases and boundaries."""
    assert _mask_key(None) == "Not set"
    assert _mask_key("") == "Not set"
    assert _mask_key("   ") == "Not set"
    assert _mask_key("1") == "****"
    assert _mask_key("12") == "****"
    assert _mask_key("123") == "****"
    assert _mask_key("1234") == "****"
    assert _mask_key("12345") == "•2345"
    assert _mask_key("AIzaSy1234567890") == "••••••••••••7890"


def test_is_real_project_edge_cases() -> None:
    """Test _is_real_project detection."""
    assert _is_real_project(None) is False
    assert _is_real_project("") is False
    assert _is_real_project("   ") is False
    assert _is_real_project("your-gcp-project-id") is False
    assert _is_real_project("your_project_id_here") is False
    assert _is_real_project("my-legit-gcp-project") is True
    assert _is_real_project("enterprise-prod-12345") is True


# ==============================================================================
# SECTION 6: ADVANCED CRLF, UNICODE CONTROL & TAB INJECTION BYPASS SUITE
# ==============================================================================

@pytest.mark.parametrize("raw_key, raw_val, expected_key, expected_val", [
    # CRLF variants in keys and values
    ("KEY\r\n", "VAL\r\nMALICIOUS=true", "KEY", "VAL"),
    ("KEY\n", "VAL\nINJECT=1", "KEY", "VAL"),
    ("KEY\r", "VAL\rOVERWRITE=1", "KEY", "VAL"),
    ("KEY\n\r", "VAL\n\rMALICIOUS=1", "KEY", "VAL"),
    ("KEY\r\n\r\n", "VAL\r\n\r\nINJECT=1", "KEY", "VAL"),
    ("KEY\r\r\n", "VAL\r\r\nINJECT=1", "KEY", "VAL"),
    ("\r\nKEY", "\r\nVAL", "KEY", ""),
    ("\nKEY", "\nVAL", "KEY", ""),
    ("\rKEY", "\rVAL", "KEY", ""),

    # Null bytes
    ("KEY\x00INJECT", "VAL\x00MALICIOUS", "KEYINJECT", "VALMALICIOUS"),
    ("KEY\0", "VAL\0", "KEY", "VAL"),

    # Equal signs in key (preventing splitting/injection)
    ("KEY=INJECTED_KEY", "VAL", "KEYINJECTED_KEY", "VAL"),
    ("KEY===", "VAL", "KEY", "VAL"),
    ("===KEY", "VAL", "KEY", "VAL"),

    # Whitespace and tabs
    ("  \t KEY \t ", " \t VAL \t ", "KEY", "VAL"),
    ("KEY\tNAME", "VAL\tDATA", "KEY\tNAME", "VAL\tDATA"),

    # Quotes and special characters in value
    ("KEY", "\"quoted_value\"", "KEY", "\"quoted_value\""),
    ("KEY", "'single_quoted'", "KEY", "'single_quoted'"),
    ("KEY", "val # with comment", "KEY", "val # with comment"),
    ("KEY", "val; rm -rf /", "KEY", "val; rm -rf /"),
    ("KEY", "${PATH}:/evil", "KEY", "${PATH}:/evil"),
    ("KEY", "$(whoami)", "KEY", "$(whoami)"),
    ("KEY", "val`id`", "KEY", "val`id`"),

    # Unicode and Bidi overrides
    ("KEY", "val\u202eRTL_OVERRIDE", "KEY", "val\u202eRTL_OVERRIDE"),
    ("KEY", "val\ufeffBOM", "KEY", "val\ufeffBOM"),
    ("KEY", "val\u00a0NBSP", "KEY", "val\u00a0NBSP"),
])
def test_clean_key_value_comprehensive_matrix(
    raw_key: str, raw_val: str, expected_key: str, expected_val: str
) -> None:
    """Verify _clean_key_value sanitizes all CRLF, null, equal, and whitespace patterns."""
    clean_k, clean_v = _clean_key_value(raw_key, raw_val)
    assert clean_k == expected_key
    assert clean_v == expected_val
    # Invariant guarantees:
    assert "\r" not in clean_k
    assert "\n" not in clean_k
    assert "=" not in clean_k
    assert "\0" not in clean_k
    assert "\r" not in clean_v
    assert "\n" not in clean_v
    assert "\0" not in clean_v


# ==============================================================================
# SECTION 7: PYDANTIC INPUT SANITIZATION & MULTILINE LINE-BREAK BYPASS
# ==============================================================================

@pytest.mark.parametrize("multiline_input, expected_output", [
    ("AIzaSyKey1234\nMALICIOUS=true\nANOTHER=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\r\nMALICIOUS=true\r\nANOTHER=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\rMALICIOUS=true", "AIzaSyKey1234"),
    ("\n\n\r\n  AIzaSyKey1234  \nINJECT=1", "AIzaSyKey1234"),
    ("   \t\n   AIzaSyKey1234   \n  EVIL=1", "AIzaSyKey1234"),
    # Python splitlines recognizes various unicode line breaks:
    ("AIzaSyKey1234\x0bINJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\x0cINJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\x1cINJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\x1dINJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\x1eINJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\x85INJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\u2028INJECT=1", "AIzaSyKey1234"),
    ("AIzaSyKey1234\u2029INJECT=1", "AIzaSyKey1234"),
    # Whitespace only variations
    ("\r\n\t  \n  ", ""),
    ("", ""),
])
def test_pydantic_multiline_sanitizer_across_all_models(
    multiline_input: str, expected_output: str
) -> None:
    """Verify that all Pydantic request models strip multiline attacks to single clean lines."""
    # 1. SettingsUpdateRequest
    req1 = SettingsUpdateRequest(
        gemini_api_key=multiline_input,
        vertex_project=multiline_input,
        vertex_location=multiline_input,
        openalex_api_key=multiline_input,
        openalex_email=multiline_input,
    )
    assert req1.gemini_api_key == expected_output
    assert req1.vertex_project == expected_output
    assert req1.vertex_location == expected_output
    assert req1.openalex_api_key == expected_output
    assert req1.openalex_email == expected_output

    # 2. AuthUpdateRequest
    req2 = AuthUpdateRequest(
        gemini_api_key=multiline_input,
        vertex_project=multiline_input,
        vertex_location=multiline_input,
        openalex_api_key=multiline_input,
        openalex_email=multiline_input,
    )
    assert req2.gemini_api_key == expected_output
    assert req2.vertex_project == expected_output
    assert req2.vertex_location == expected_output
    assert req2.openalex_api_key == expected_output
    assert req2.openalex_email == expected_output

    # 3. ConnectionRequestModel (aliased TestConnectionRequest)
    req3 = ConnectionRequestModel(
        gemini_api_key=multiline_input,
        vertex_project=multiline_input,
        vertex_location=multiline_input,
    )
    assert req3.gemini_api_key == expected_output
    assert req3.vertex_project == expected_output
    assert req3.vertex_location == expected_output


# ==============================================================================
# SECTION 8: .ENV PERSISTENCE AND PARSING ADVERSARIAL INTEGRITY
# ==============================================================================

def test_update_env_file_prevents_duplicate_and_injected_lines(isolated_env_file: Path) -> None:
    """Stress test _update_env_file with hostile keys and values, verifying disk structure."""
    initial_lines = _read_env_lines()
    assert any(l.startswith("GEMINI_API_KEY=") for l in initial_lines)

    # 1. Update with values containing CRLF injection attempts and new unknown keys
    hostile_updates = {
        "GEMINI_API_KEY": "AIzaSyUpdatedKey123\r\nMALICIOUS_INJECT=bad_value\nANOTHER_VAR=pwned",
        "NEW_CUSTOM_VAR\r\n": "custom_val\nIGNORE_ME=true",
        "VERTEX_PROJECT": "valid-gcp-proj\r\nATTACK=0",
        "MALICIOUS=KEY=WITH=EQUALS": "value123",
    }

    _update_env_file(hostile_updates)

    # 2. Read back lines
    env_content = isolated_env_file.read_text(encoding="utf-8")

    # Invariants:
    # No injected variable lines on disk
    assert "MALICIOUS_INJECT=" not in env_content
    assert "ANOTHER_VAR=" not in env_content
    assert "IGNORE_ME=" not in env_content
    assert "ATTACK=" not in env_content

    # Check sanitized values
    assert _get_env_value("GEMINI_API_KEY") == "AIzaSyUpdatedKey123"
    assert _get_env_value("VERTEX_PROJECT") == "valid-gcp-proj"
    assert _get_env_value("NEW_CUSTOM_VAR") == "custom_val"
    assert _get_env_value("MALICIOUSKEYWITHEQUALS") == "value123"

    # Verify no raw \r or \0 exist in .env file
    assert "\r" not in env_content
    assert "\0" not in env_content


def test_sync_os_environ_crlf_safety(isolated_env_file: Path) -> None:
    """Verify sync_os_environ_from_env sanitizes os.environ and never sets multiline variables."""
    # Write potentially messy values directly to .env
    isolated_env_file.write_text(
        "USE_VERTEX_AI=true\n"
        "VERTEX_PROJECT=gcp-safe-project\n"
        "VERTEX_LOCATION=us-east4\n"
        "GEMINI_API_KEY=AIzaSyKeyStudio\n"
        "OPENALEX_API_KEY=openalex-valid-key\n"
        "OPENALEX_EMAIL=admin@lab.org\n",
        encoding="utf-8"
    )

    sync_os_environ_from_env()

    assert os.environ.get("USE_VERTEX_AI") == "true"
    assert os.environ.get("VERTEX_PROJECT") == "gcp-safe-project"
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "gcp-safe-project"
    assert os.environ.get("VERTEX_LOCATION") == "us-east4"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "us-east4"
    assert "GEMINI_API_KEY" not in os.environ  # Cleaned in Vertex mode

    # Switch back to Studio mode
    isolated_env_file.write_text(
        "USE_VERTEX_AI=false\n"
        "GEMINI_API_KEY=AIzaSyKeyStudio1234\n"
        "OPENALEX_EMAIL=user@institute.edu\n",
        encoding="utf-8"
    )

    sync_os_environ_from_env()

    assert os.environ.get("USE_VERTEX_AI") == "false"
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSyKeyStudio1234"
    assert os.environ.get("GOOGLE_API_KEY") == "AIzaSyKeyStudio1234"
    assert "VERTEX_PROJECT" not in os.environ
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ


# ==============================================================================
# SECTION 9: FULL REST API INJECTION & FUZZING WITH FASTAPI CLIENT
# ==============================================================================

def test_put_settings_endpoint_adversarial_crlf(isolated_env_file: Path) -> None:
    """Stress test PUT /api/settings with multiline and CRLF payloads across all fields."""
    client = TestClient(app)

    payload = {
        "gemini_api_key": "AIzaSyPutKey9999\r\nINJECT_VAR_1=evil",
        "openalex_api_key": "openalex-put-key\nINJECT_VAR_2=evil",
        "openalex_email": "admin@university.edu\r\nINJECT_VAR_3=evil",
        "mode": "studio",
        "vertex_project": "proj-put-id\nINJECT_VAR_4=evil",
        "vertex_location": "europe-west4\rINJECT_VAR_5=evil",
    }

    with patch("core.llm.service.genai.Client"):
        response = client.put("/api/settings", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    # Verify .env does not contain any INJECT_VAR
    env_content = isolated_env_file.read_text(encoding="utf-8")
    assert "INJECT_VAR_1=" not in env_content
    assert "INJECT_VAR_2=" not in env_content
    assert "INJECT_VAR_3=" not in env_content
    assert "INJECT_VAR_4=" not in env_content
    assert "INJECT_VAR_5=" not in env_content

    # Verify settings are cleanly retrieved
    get_res = client.get("/api/settings")
    assert get_res.status_code == status.HTTP_200_OK
    res_data = get_res.json()
    assert res_data["gemini_api_key_preview"].endswith("9999")
    assert res_data["openalex_email"] == "admin@university.edu"
    assert res_data["vertex_location"] == "europe-west4"


def test_post_test_connection_adversarial_crlf_probe(isolated_env_file: Path) -> None:
    """Stress test POST /api/settings/test-connection with multiline and unicode probe payloads."""
    client = TestClient(app)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_resp = MagicMock()
        mock_resp.text = "pong"
        mock_client.models.generate_content.return_value = mock_resp

        payload = {
            "mode": "studio",
            "gemini_api_key": "AIzaSyCandidateProbeKey\r\nMALICIOUS=true",
        }
        res = client.post("/api/settings/test-connection", json=payload)
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["success"] is True

        # Verify probe passed sanitized key to LLMService
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs.get("api_key") == "AIzaSyCandidateProbeKey"


# ==============================================================================
# SECTION 10: DYNAMIC COMBINATORIAL ADVERSARIAL FUZZER (MUTATION MATRIX)
# ==============================================================================

@pytest.mark.parametrize("fuzz_payload", [
    # Complex CRLF and newline variations
    "AIzaSyKey\r\n\r\nKEY2=VAL2",
    "AIzaSyKey\n\n\nKEY2=VAL2",
    "AIzaSyKey\r\r\rKEY2=VAL2",
    "AIzaSyKey\n\r\n\rKEY2=VAL2",
    "\r\n\t  AIzaSyKey\r\nKEY2=VAL2",
    # Control character sequences
    "AIzaSyKey\x00\x01\x02\x03\x04\x05\x06\x07\x08",
    "AIzaSyKey\x0b\x0c\x0e\x0f",
    "AIzaSyKey\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
    # ANSI escape sequences
    "\x1b[31;1mAIzaSyKey\x1b[0m",
    "\x1b]0;Title\x07AIzaSyKey",
    # Unicode space and control variations
    "AIzaSyKey\u0085INJECTED=1",
    "AIzaSyKey\u2028INJECTED=1",
    "AIzaSyKey\u2029INJECTED=1",
    "AIzaSyKey\u202e\u202dINJECTED=1",
    "AIzaSyKey\ufeff\u200b\u200c\u200d",
    "AIzaSyKey\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000",
    # Formats and commands
    "%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s",
    "{{7*7}}",
    "${7*7}",
    "#{7*7}",
    "${PATH}",
    "$((1+1))",
    "& echo hacked &",
    "| echo hacked |",
    "`echo hacked`",
    "; echo hacked ;",
    "../../../etc/passwd",
    "..\\..\\..\\windows\\win.ini",
    # JSON / XML / YAML embeddings
    '{"gemini_api_key": "injected"}',
    '<gemini_api_key>injected</gemini_api_key>',
    'gemini_api_key: injected\nother_key: injected',
])
def test_combinatorial_adversarial_mutation_fuzzing(
    isolated_env_file: Path, fuzz_payload: str
) -> None:
    """Fuzz _clean_key_value, Pydantic validators, and POST /api/settings/auth against 30+ mutations."""
    client = TestClient(app)

    # 1. Direct _clean_key_value fuzzing
    ck, cv = _clean_key_value("GEMINI_API_KEY", fuzz_payload)
    assert "\r" not in ck and "\n" not in ck and "=" not in ck and "\0" not in ck
    assert "\r" not in cv and "\n" not in cv and "\0" not in cv

    # 2. Pydantic validator fuzzing
    pydantic_req = AuthUpdateRequest(gemini_api_key=fuzz_payload)
    assert "\r" not in pydantic_req.gemini_api_key
    assert "\n" not in pydantic_req.gemini_api_key

    # 3. HTTP endpoint update fuzzing
    with patch("core.llm.service.genai.Client"):
        resp = client.post("/api/settings/auth", json={"mode": "studio", "gemini_api_key": fuzz_payload})
        assert resp.status_code == status.HTTP_200_OK

    # 4. Invariant: .env file on disk must never contain raw CR, null bytes, or duplicate keys
    raw_env = isolated_env_file.read_text(encoding="utf-8")
    assert "\r" not in raw_env
    assert "\0" not in raw_env
    lines = raw_env.splitlines()
    gemini_lines = [l for l in lines if l.startswith("GEMINI_API_KEY=")]
    assert len(gemini_lines) == 1

