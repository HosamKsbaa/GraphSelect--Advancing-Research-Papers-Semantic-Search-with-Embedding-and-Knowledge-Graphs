"""Outline tools alias forwarding to agents.planner.tools.outline_tools."""
from __future__ import annotations

from agents.planner.tools.outline_tools import (
    generate_outline,
    get_project_summary,
    get_ranked_papers,
)

__all__ = [
    "get_project_summary",
    "get_ranked_papers",
    "generate_outline",
]
