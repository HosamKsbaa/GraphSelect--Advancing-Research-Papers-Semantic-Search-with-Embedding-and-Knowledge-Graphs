"""LLM completion Pydantic models for ALRS v2.

Provides request/response shapes for the Gemini-backed LLM service,
including structured output support via generics.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class TokenUsage(BaseModel):
    """Token usage statistics for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionRequest(BaseModel):
    """Request payload for an LLM completion call."""

    prompt: str = Field(..., min_length=1, description="The user/task prompt")
    system_instruction: str | None = Field(
        default=None,
        description="Optional system-level instruction for the model",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        le=65536,
        description="Maximum output tokens",
    )
    response_format: str | None = Field(
        default=None,
        description="Response MIME type (e.g. 'application/json')",
    )


class CompletionResponse(BaseModel):
    """Response from a single LLM completion call."""

    text: str = Field(..., description="Generated text content")
    usage: TokenUsage = Field(default_factory=TokenUsage)


class StructuredOutput(BaseModel, Generic[T]):
    """Wrapper for structured (JSON-parsed) LLM output.

    Attributes:
        data: The parsed Pydantic model of type T.
        raw_text: The raw text returned by the LLM before parsing.
    """

    data: T
    raw_text: str = ""
