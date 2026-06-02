"""ALRS v2 agentic research workflow agents.

This package houses the Google ADK-based agents that implement the
multi-agent research pipeline:

- **ProjectAgent** (orchestrator): Top-level coordinator.
- **ResearchAgent**: Coordinates literature discovery and analysis.
  - **ALRSAgent**: Paper search and discovery via OpenAlex.
  - **GapFinderAgent**: Coverage analysis, gap detection, hybrid ranking.

Agent hierarchy::

    ProjectAgent (orchestrator)
    └── ResearchAgent (coordinator)
        ├── ALRSAgent (paper discovery)
        └── GapFinderAgent (analysis & ranking)

Each agent is built on the ``google.adk`` framework and communicates
via structured tool calls and shared project state.  Services are
accessed through the ``_service_registry.ServiceRegistry`` singleton.
"""
from __future__ import annotations

__all__: list[str] = [
    "create_root_agent",
]

from agents.agent import create_root_agent
