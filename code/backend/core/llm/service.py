"""LLM service for ALRS v2 using Google Gemini.

Provides completion and structured JSON output with exponential backoff
retry logic. Uses the ``google.genai`` client directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
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


class LLMService:
    """Central service for Gemini LLM calls with retry and structured output.

    Provides prompt completion and JSON-structured output parsing with
    automatic exponential backoff on transient errors (429, 503).
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.5-flash",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a text completion from the Gemini model.

        Uses exponential backoff with up to 3 retries on transient errors.

        Args:
            request: The completion request parameters.

        Returns:
            CompletionResponse with generated text and token usage.

        Raises:
            Exception: After all retries are exhausted.
        """
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
