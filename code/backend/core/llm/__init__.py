"""ALRS v2 LLM service module.

Provides the ``LLMService`` for Gemini completions and the Pydantic
models (``CompletionRequest``, ``CompletionResponse``, ``StructuredOutput``)
for typed LLM interactions.
"""
from __future__ import annotations

from core.llm.models import CompletionRequest, CompletionResponse, StructuredOutput, TokenUsage
from core.llm.service import LLMService

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "LLMService",
    "StructuredOutput",
    "TokenUsage",
]
