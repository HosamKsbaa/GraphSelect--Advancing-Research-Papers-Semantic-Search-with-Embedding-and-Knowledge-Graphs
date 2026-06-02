"""Orchestrator agent sub-package with tracing and token budget callbacks.

Contains the ProjectAgent (orchestrator), tracing callback factories,
and token budget enforcement logic for agent execution.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from google.genai import types

if TYPE_CHECKING:
    from google.adk.models import LlmResponse
    from google.adk.tools import BaseTool

    from core.logging.log_service import LogService

logger = logging.getLogger(__name__)


def create_tracing_callbacks(
    log_service: LogService,
    project_id: str,
    token_budget: int = 500_000,
    warn_threshold: float = 0.8,
) -> dict[str, Any]:
    """Create ADK callback functions for tracing AND token budget enforcement.

    Returns a dict of callback functions that can be spread into an
    LlmAgent constructor.  The callbacks:
    1. Log LLM calls and tool calls to the agent_traces MySQL table.
    2. Track cumulative token usage and enforce budget limits.

    Args:
        log_service: The LogService instance for trace persistence.
        project_id: The project UUID for trace correlation.
        token_budget: Maximum tokens allowed per pipeline run (default 500K).
        warn_threshold: Fraction of budget at which to warn (default 0.8).

    Returns:
        Dict with keys 'after_model_callback' and 'after_tool_callback',
        each mapping to an async callback function.
    """
    # Mutable state shared across callbacks
    _state: dict[str, Any] = {
        "total_tokens": 0,
        "budget": token_budget,
        "warned": False,
    }

    async def after_model_callback(
        callback_context: Any,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Log LLM call and enforce token budget.

        Returns:
            - None if within budget (no modification).
            - A Content object with stop message if budget exhausted.
        """
        try:
            agent_name = "unknown"
            if hasattr(callback_context, "agent_name"):
                agent_name = callback_context.agent_name
            elif hasattr(callback_context, "agent") and hasattr(
                callback_context.agent, "name"
            ):
                agent_name = callback_context.agent.name

            # Extract token count
            token_count = 0
            if (
                hasattr(llm_response, "usage_metadata")
                and llm_response.usage_metadata
            ):
                token_count = (
                    getattr(
                        llm_response.usage_metadata, "total_token_count", 0
                    )
                    or 0
                )

            _state["total_tokens"] += token_count

            # Extract text length for logging
            text_len = 0
            if hasattr(llm_response, "content") and llm_response.content:
                parts = getattr(llm_response.content, "parts", [])
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        text_len += len(part.text)

            await log_service.log_agent_trace(
                project_id=project_id,
                agent_name=agent_name,
                event_type="llm_call",
                token_count=token_count,
                details={
                    "response_text_length": text_len,
                    "cumulative_tokens": _state["total_tokens"],
                    "budget": _state["budget"],
                },
            )

            # --- Token budget enforcement (T054) ---
            used_fraction = (
                _state["total_tokens"] / _state["budget"]
                if _state["budget"] > 0
                else 0
            )

            if used_fraction >= 1.0:
                logger.warning(
                    "Token budget EXHAUSTED: %d / %d",
                    _state["total_tokens"],
                    _state["budget"],
                )
                # Return a content that tells agents to stop
                return types.Content(
                    parts=[
                        types.Part.from_text(
                            "⚠️ TOKEN BUDGET EXHAUSTED "
                            f"({_state['total_tokens']:,} / "
                            f"{_state['budget']:,} tokens used). "
                            "PAUSE all agent activity immediately. "
                            "Preserve all completed work and present "
                            "a progress summary to the user. "
                            "Offer to resume with an increased budget."
                        )
                    ]
                )
            elif used_fraction >= warn_threshold and not _state["warned"]:
                _state["warned"] = True
                logger.info(
                    "Token budget warning: %d / %d (%.0f%%)",
                    _state["total_tokens"],
                    _state["budget"],
                    used_fraction * 100,
                )

        except Exception as exc:
            logger.warning("after_model_callback tracing failed: %s", exc)

        return None  # Proceed normally

    async def after_tool_callback(
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: Any,
        tool_response: Any,
    ) -> dict[str, Any] | None:
        """Log tool call details after tool execution.

        Returns:
            None — does not modify the tool response.
        """
        try:
            tool_name = getattr(tool, "name", str(tool))
            agent_name = "unknown"
            if hasattr(tool_context, "agent_name"):
                agent_name = tool_context.agent_name
            elif hasattr(tool_context, "agent") and hasattr(
                tool_context.agent, "name"
            ):
                agent_name = tool_context.agent.name

            # Summarize args (truncate large values)
            args_summary: dict[str, str] = {}
            for k, v in args.items():
                v_str = str(v)
                args_summary[k] = v_str[:200] if len(v_str) > 200 else v_str

            await log_service.log_agent_trace(
                project_id=project_id,
                agent_name=agent_name,
                event_type="tool_call",
                token_count=0,
                details={
                    "tool_name": tool_name,
                    "args": args_summary,
                },
            )
        except Exception as exc:
            logger.warning("after_tool_callback tracing failed: %s", exc)

        return None  # Don't modify the tool response

    return {
        "after_model_callback": after_model_callback,
        "after_tool_callback": after_tool_callback,
    }


__all__: list[str] = ["create_tracing_callbacks"]
