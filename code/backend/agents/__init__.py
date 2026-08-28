"""ALRS v2 agentic research workflow agents.

This package houses the Google ADK-based agents that implement the
multi-agent research pipeline:

- **ProjectAgent** (orchestrator): Top-level coordinator.
- **ResearchAgent**: Coordinates literature discovery and analysis.
  - **ALRSAgent**: Paper search and discovery via OpenAlex.
  - **GapFinderAgent**: Coverage analysis, gap detection, hybrid ranking.
  - **EvidenceSynthesizerAgent**: Literature matrix extraction and synthesis.
- **PlannerAgent**: Outline generation and topic structuring.
- **WriterAgent**: Literature review drafting, peer review, and export.
  - **DraftingAgent**: Section drafting with citation verification.
  - **ReviewerAgent**: Section evaluation and feedback loops.
- **DebuggerAgent**: Autonomous system diagnostic and code repair specialist.

Agent hierarchy::

    ProjectAgent (orchestrator)
    ├── ResearchAgent (coordinator)
    │   ├── ALRSAgent (paper discovery & OpenAlex)
    │   ├── GapFinderAgent (analysis, ranking & coverage)
    │   └── EvidenceSynthesizerAgent (literature matrix synthesis)
    ├── PlannerAgent (outline generation)
    ├── WriterAgent (writing & export)
    │   └── WriterReviewerLoop (LoopAgent)
    │       ├── DraftingAgent (section drafting)
    │       └── ReviewerAgent (peer review & loop exit)
    └── DebuggerAgent (autonomous diagnostics, log inspection & AST patches)

Each agent is built on the ``google.adk`` framework and communicates
via structured tool calls and shared project state.  Services are
accessed through the ``_service_registry.ServiceRegistry`` singleton.
"""
from __future__ import annotations

from agents.agent import (
    DebuggerAgent,
    create_debugger_agent,
    create_root_agent,
    debugger_agent,
    root_agent,
)

__all__: list[str] = [
    "create_root_agent",
    "root_agent",
    "DebuggerAgent",
    "debugger_agent",
    "create_debugger_agent",
]
