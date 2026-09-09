"""LLM service for ALRS v2 using Google Gemini.

Provides completion, structured JSON output, dual-mode client initialization
(Google AI Studio vs Google Cloud Vertex AI), and live connection testing.
Uses the ``google.genai`` client directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from functools import partial
from typing import Any, TypeVar

from google import genai
from google.genai import types

from core.llm.models import (
    CompletionRequest,
    CompletionResponse,
    StructuredOutput,
    TokenUsage,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES: int = 3
BASE_BACKOFF_SECONDS: float = 1.0

# Sentinels representing unconfigured / placeholder states
_PLACEHOLDERS = {"", "your_gemini_api_key_here", "your_project_id_here", "your-gcp-project-id", "Not set", "None", "null"}


class LLMService:
    """Central service for Gemini LLM calls with retry, structured output, and dual-mode auth.

    Supports both Google AI Studio (API key) and Google Cloud Vertex AI (Project + Location + ADC).
    """

    def __init__(
        self,
        api_key: str | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        model_name: str | None = None,
        log_service: Any | None = None,
    ) -> None:
        """Initialize the LLM service with explicit parameters or system settings."""
        from config import get_settings
        settings = get_settings()

        # Determine mode
        self._use_vertex_ai: bool = vertexai if vertexai is not None else settings.use_vertex_ai
        self._model_name: str = model_name or settings.adk_model_name or "gemini-3.5-flash"
        self._log_service = log_service
        self._client: genai.Client | None = None
        self._init_error: str | None = None
        self._project: str | None = None
        self._location: str | None = None
        self._api_key: str | None = None

        if self._use_vertex_ai:
            self._mode = "vertex"
            self._project = (
                project or (settings.vertex_project if settings.vertex_project and settings.vertex_project not in _PLACEHOLDERS else None) or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
            ).strip()
            self._location = (
                location or settings.vertex_location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
            ).strip()
            self._api_key = None

            if self._project and self._project not in _PLACEHOLDERS:
                try:
                    self._client = genai.Client(
                        vertexai=True,
                        project=self._project,
                        location=self._location,
                    )
                    logger.info(
                        "LLMService initialized via Vertex AI (project=%s, location=%s, model=%s)",
                        self._project, self._location, self._model_name,
                    )
                except Exception as exc:
                    self._client = None
                    self._init_error = f"Vertex AI initialization failed: {exc}"
                    logger.warning("LLMService failed to initialize Vertex AI client: %s", exc)
            else:
                self._client = None
                self._init_error = "Vertex AI project ID not configured"
                logger.warning("LLMService initialized in Vertex AI mode without a configured GCP project")
        else:
            self._mode = "studio"
            self._project = None
            self._location = None
            effective_key = (
                api_key
                or (settings.gemini_api_key if settings.gemini_api_key and settings.gemini_api_key not in _PLACEHOLDERS else None)
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or ""
            ).strip()
            if effective_key in _PLACEHOLDERS:
                effective_key = ""

            self._api_key = effective_key or None


            if self._api_key:
                try:
                    self._client = genai.Client(api_key=self._api_key, vertexai=False)
                    logger.info("LLMService initialized via Google AI Studio (model=%s)", self._model_name)
                except Exception as exc:
                    self._client = None
                    self._init_error = f"Google AI Studio initialization failed: {exc}"
                    logger.warning("LLMService failed to initialize Google AI Studio client: %s", exc)
            else:
                self._client = None
                self._init_error = "Gemini API key not configured"
                logger.warning("LLMService initialized without credentials (GEMINI_API_KEY not configured)")

    # ── Inspection Properties ────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Return True if a valid genai.Client instance is active."""
        return self._client is not None

    @property
    def is_vertex_ai(self) -> bool:
        """Return True if active auth mode is Vertex AI."""
        return self._mode == "vertex"

    @property
    def mode(self) -> str:
        """Return the active auth mode ('studio' or 'vertex')."""
        return self._mode

    @property
    def project(self) -> str | None:
        """Return the active GCP Project ID when in Vertex AI mode."""
        return self._project

    @property
    def location(self) -> str | None:
        """Return the active GCP Location when in Vertex AI mode."""
        return self._location

    @property
    def client(self) -> genai.Client | None:
        """Return the underlying google.genai.Client instance."""
        return self._client

    @property
    def model_name(self) -> str:
        """Return the active completion model name."""
        return self._model_name

    # ── Connectivity Test Probe ──────────────────────────────────────

    @classmethod
    async def test_connection(
        cls,
        mode: str = "studio",
        api_key: str | None = None,
        project: str | None = None,
        location: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Probe Gemini API connectivity with temporary or configured credentials.

        Executes a minimal test generation ('ping') and records round-trip latency.
        """
        is_vertex = str(mode).lower() in ("vertex", "vertex_ai", "vertexai")
        target_mode = "vertex" if is_vertex else "studio"
        target_model = model_name or "gemini-3.5-flash"

        # 1. Instantiate probe client
        try:
            if is_vertex:
                if project is not None:
                    proj = project.strip()
                else:
                    proj = (os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()

                if not proj or proj in _PLACEHOLDERS:
                    return {
                        "success": False,
                        "error": "Google Cloud Project ID is not configured for Vertex AI",
                        "message": "Connection failed",
                        "model": target_model,
                        "mode": target_mode,
                        "details": "Enter a valid GCP Project ID.",
                    }
                if location is not None and location.strip():
                    loc = location.strip()
                else:
                    loc = (os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()

                probe_client = genai.Client(
                    vertexai=True,
                    project=proj,
                    location=loc,
                )
            else:
                if api_key is not None:
                    key = api_key.strip()
                else:
                    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()

                if not key or key in _PLACEHOLDERS:
                    return {
                        "success": False,
                        "error": "Gemini API key is not configured for Google AI Studio",
                        "message": "Connection failed",
                        "model": target_model,
                        "mode": target_mode,
                        "details": "Get a free API key at https://aistudio.google.com/",
                    }
                probe_client = genai.Client(api_key=key, vertexai=False)
        except Exception as exc:
            err_msg = str(exc)
            if "DefaultCredentialsError" in type(exc).__name__ or "credentials" in err_msg.lower():
                err_msg = "Application Default Credentials (ADC) not found. Run 'gcloud auth application-default login'."
            return {
                "success": False,
                "error": f"Client initialization failed: {err_msg}",
                "message": "Connection failed",
                "model": target_model,
                "mode": target_mode,
            }

        # 2. Perform live probe ping
        loop = asyncio.get_running_loop()
        start_time = time.monotonic()
        config = types.GenerateContentConfig(
            max_output_tokens=5,
            temperature=0.0,
        )

        try:
            func = partial(
                probe_client.models.generate_content,
                model=target_model,
                contents="ping",
                config=config,
            )
            await loop.run_in_executor(None, func)
            latency_ms = round((time.monotonic() - start_time) * 1000, 1)
            return {
                "success": True,
                "message": f"Connection established successfully ({'Vertex AI' if is_vertex else 'Google AI Studio'})",
                "model": target_model,
                "latency_ms": latency_ms,
                "mode": target_mode,
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - start_time) * 1000, 1)
            err_str = str(exc)
            code = getattr(exc, "code", getattr(exc, "status_code", 0))

            if is_vertex:
                # Vertex AI Error Mapping
                if "DefaultCredentialsError" in type(exc).__name__ or "could not automatically determine credentials" in err_str.lower():
                    clean_error = "Missing Google Cloud Application Default Credentials. Run 'gcloud auth application-default login'."
                    details = "Run 'gcloud auth application-default login' to authenticate with Vertex AI."
                elif "PERMISSION_DENIED" in err_str or code == 403:
                    clean_error = "Permission denied. Ensure Vertex AI API (aiplatform.googleapis.com) is enabled and you have necessary IAM permissions."
                    details = "Enable the API with 'gcloud services enable aiplatform.googleapis.com'."
                elif "RESOURCE_EXHAUSTED" in err_str or code == 429:
                    clean_error = "Vertex AI quota exceeded (HTTP 429). Check your Google Cloud quotas in the GCP Console."
                    details = "Check quotas and billing at https://console.cloud.google.com/iam-admin/quotas"
                elif "NOT_FOUND" in err_str or code == 404:
                    clean_error = f"Model '{target_model}' was not found or is unavailable in the specified GCP region/project."
                    details = "Ensure the model is available in your Vertex AI region."
                else:
                    clean_error = f"Vertex AI connection failed: {err_str}"
                    details = None
            else:
                # Google AI Studio Error Mapping
                if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_str or code == 401 or "UNAUTHENTICATED" in err_str:
                    clean_error = "Invalid Gemini API key format. Google AI Studio keys start with 'AIzaSy...'. Please ensure you copied your key from https://aistudio.google.com/apikey (not an OpenAlex key)."
                    details = "Generate a free Gemini API key at https://aistudio.google.com/apikey"
                elif "API_KEY_INVALID" in err_str or "API key not valid" in err_str or code == 400:
                    clean_error = "Invalid Gemini API key. Please check your API key in Google AI Studio."
                    details = "Verify your API key at https://aistudio.google.com/"
                elif "PERMISSION_DENIED" in err_str or code == 403:
                    clean_error = "Permission denied for Google AI Studio API key. Ensure the key is active and has permission to access the Gemini API."
                    details = "Check API key restrictions in Google AI Studio or Google Cloud Console (https://aistudio.google.com/)."
                elif "RESOURCE_EXHAUSTED" in err_str or code == 429:
                    clean_error = "Quota exceeded (HTTP 429). Google AI Studio rate limit or quota exceeded."
                    details = "Check your rate limits and quotas at https://aistudio.google.com/"
                elif "NOT_FOUND" in err_str or code == 404:
                    clean_error = f"Model '{target_model}' was not found in Google AI Studio."
                    details = "Ensure you are using a supported model like 'gemini-3.5-flash' or 'gemini-2.5-flash'."
                else:
                    clean_error = f"Google AI Studio connection failed: {err_str}"
                    details = None

            return {
                "success": False,
                "error": clean_error,
                "message": f"Connection failed: {clean_error}",
                "model": target_model,
                "latency_ms": latency_ms,
                "mode": target_mode,
                "details": details,
            }

    # ── Completion Methods ───────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a text completion from the Gemini model.

        Uses exponential backoff with up to 3 retries on transient errors.

        Args:
            request: The completion request parameters.

        Returns:
            CompletionResponse with generated text and token usage.

        Raises:
            ValueError: If credentials are missing.
            Exception: After all retries are exhausted.
        """
        if self._client is None:
            if self._mode == "vertex":
                raise ValueError(
                    "Vertex AI is enabled but project ID is missing or Application Default Credentials (ADC) are not set. "
                    "Please configure GCP_PROJECT_ID in Settings or run 'gcloud auth application-default login'."
                )
            else:
                raise ValueError(
                    "Gemini API key is not configured. Please add your GEMINI_API_KEY in Settings or .env file."
                )

        loop = asyncio.get_running_loop()

        config = types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )
        if request.system_instruction:
            config.system_instruction = request.system_instruction
        if request.response_format:
            config.response_mime_type = request.response_format

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            start_ms = int(time.monotonic() * 1000)
            try:
                func = partial(
                    self._client.models.generate_content,
                    model=self._model_name,
                    contents=request.prompt,
                    config=config,
                )
                result = await loop.run_in_executor(None, func)
                elapsed_ms = int(time.monotonic() * 1000) - start_ms

                text = result.text or ""

                # Extract usage from response metadata
                usage = TokenUsage()
                if hasattr(result, "usage_metadata") and result.usage_metadata:
                    meta = result.usage_metadata
                    usage = TokenUsage(
                        prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                        completion_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                        total_tokens=getattr(meta, "total_token_count", 0) or 0,
                    )

                logger.debug(
                    "LLM completion: %d chars in %dms (tokens: %d)",
                    len(text),
                    elapsed_ms,
                    usage.total_tokens,
                )
                return CompletionResponse(text=text, usage=usage)

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "code", getattr(exc, "status_code", 0))
                if status_code in (429, 503) and attempt < MAX_RETRIES:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        "LLM call failed (attempt %d/%d, status %s): %s — retrying in %.1fs",
                        attempt + 1, MAX_RETRIES + 1, status_code, exc, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

                if status_code == 429 and self._model_name != "gemini-3.5-flash-lite":
                    logger.warning(
                        "LLM call 429 Quota Exceeded on %s; attempting automatic fallback to gemini-3.5-flash-lite...",
                        self._model_name,
                    )
                    try:
                        fallback_func = partial(
                            self._client.models.generate_content,
                            model="gemini-3.5-flash-lite",
                            contents=request.prompt,
                            config=config,
                        )
                        result = await loop.run_in_executor(None, fallback_func)
                        text = result.text or ""
                        usage = TokenUsage()
                        if hasattr(result, "usage_metadata") and result.usage_metadata:
                            meta = result.usage_metadata
                            usage = TokenUsage(
                                prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                                completion_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                                total_tokens=getattr(meta, "total_token_count", 0) or 0,
                            )
                        return CompletionResponse(text=text, usage=usage)
                    except Exception as fb_exc:
                        logger.warning("Fallback to gemini-3.5-flash-lite failed: %s", fb_exc)

                raise

        # Should be unreachable, but satisfy type checker
        raise last_exc or RuntimeError("LLM completion failed after retries")  # pragma: no cover

    async def complete_structured(
        self,
        request: CompletionRequest,
        output_type: type[T],
    ) -> StructuredOutput[T]:
        """Generate a JSON-structured completion and parse it into a Pydantic model.

        Instructs the model to respond in JSON format and parses the result
        into the specified ``output_type``.

        Args:
            request: The completion request (prompt will be augmented with JSON instructions).
            output_type: The Pydantic model class to parse the JSON into.

        Returns:
            StructuredOutput wrapping the parsed model and raw text.

        Raises:
            ValueError: If the model output cannot be parsed as valid JSON
                        or does not match the expected schema.
        """
        # Force JSON response format
        json_request = request.model_copy(
            update={"response_format": "application/json"}
        )

        response = await self.complete(json_request)
        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first and last lines (code fence markers)
            if len(lines) >= 2:
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

        try:
            parsed_data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM returned invalid JSON: {e}\nRaw text: {raw_text[:500]}"
            ) from e

        try:
            from pydantic import TypeAdapter
            adapter = TypeAdapter(output_type)
            model_instance = adapter.validate_python(parsed_data)
        except Exception as e:
            raise ValueError(
                f"LLM JSON does not match schema {output_type.__name__}: {e}\n"
                f"Parsed data: {str(parsed_data)[:500]}"
            ) from e

        return StructuredOutput(data=model_instance, raw_text=response.text)

