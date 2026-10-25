from __future__ import annotations

from pathlib import Path
import pytest

from ai import (
    AgentToolRuntime,
    ResearchAgent,
    WriteReviewOutput,
    verify_review_citations,
)
from engines.alrs import AlrsEngine
from engines.budget import BudgetExceededError, SpendingLedger
from engines.collections import InMemoryCollectionStore, build_paper_collection
from engines.papers import Paper
from tests.ai.test_research_agent import FakeEmbeddingProvider, FakeOpenAlexProvider


def test_spending_ledger_reservation_completion_and_hard_cap(tmp_path: Path) -> None:
    ledger_file = tmp_path / "budget.json"
    ledger = SpendingLedger(limit_nano_usd=2_000_000, ledger_path=ledger_file)

    r1 = ledger.reserve("gemini_embedding", amount_nano_usd=1_500_000)
    assert ledger.committed_nano_usd == 1_500_000
    assert ledger.remaining_nano_usd == 500_000

    with pytest.raises(BudgetExceededError):
        ledger.reserve("gemini_flash", amount_nano_usd=600_000)

    ledger.complete(r1.receipt_id, actual_nano_usd=1_000_000)
    assert ledger.committed_nano_usd == 1_000_000

    reloaded = SpendingLedger(limit_nano_usd=2_000_000, ledger_path=ledger_file)
    assert reloaded.committed_nano_usd == 1_000_000
    assert len(reloaded.snapshot().calls) == 1


def test_verify_review_citations_strips_invented_dois() -> None:
    paper = Paper(
        doi="10.1000/seed",
        title="GraphSelect Retrieval",
        abstract="GraphSelect combines dense vectors with personalized PageRank.",
        year=2025,
    )
    collection = build_paper_collection(
        title="Test Collection",
        papers=[paper],
        research_questions=["How does GraphSelect work?"],
    )

    tainted_review = WriteReviewOutput(
        collection_id=str(collection.collection_id),
        markdown_review=(
            "# Review\n\nGraphSelect improves recall [10.1000/seed] "
            "and also cites an invented paper [10.9999/invented]."
        ),
        cited_dois=["10.1000/seed", "10.9999/invented"],
        apa_references=[],
        bibtex_entries=[],
        verified_findings_count=1,
    )

    report = verify_review_citations(collection, tainted_review)
    assert not report.verified
    assert report.verified_dois == ["10.1000/seed"]
    assert report.unsupported_dois == ["10.9999/invented"]
    assert "[10.1000/seed]" in report.cleaned_markdown
    assert "10.9999/invented" not in report.cleaned_markdown


@pytest.mark.asyncio
async def test_research_agent_approval_pause_resume_and_cancel() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    ledger = SpendingLedger(limit_nano_usd=10_000_000)
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
        collection_store=InMemoryCollectionStore(),
        spending_ledger=ledger,
    )
    agent = ResearchAgent(runtime)

    paused = await agent.start_run(
        topic="How does GraphSelect rank academic literature?",
        require_approval=True,
    )
    assert paused.status == "awaiting_approval"
    assert paused.seed_doi == "10.1000/seed"
    assert paused.collection_id is None
    assert paused.review_output is None

    resumed = await agent.resume_run(paused.thread_id, approved=True)
    assert resumed.status == "completed"
    assert resumed.collection_id is not None
    assert resumed.review_output is not None
    assert resumed.verification_report is not None
    assert resumed.verification_report.verified
    assert "10.1000/seed" in resumed.verification_report.verified_dois
    assert ledger.committed_nano_usd > 0

    paused_cancel = await agent.start_run(
        topic="Cancelable topic",
        require_approval=True,
    )
    cancelled = await agent.resume_run(paused_cancel.thread_id, approved=False)
    assert cancelled.status == "cancelled"
    assert cancelled.review_output is None


@pytest.mark.asyncio
async def test_research_agent_stops_when_budget_exceeded() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    tiny_ledger = SpendingLedger(limit_nano_usd=500)  # smaller than 1_000 openalex reservation
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
        spending_ledger=tiny_ledger,
    )
    agent = ResearchAgent(runtime)

    with pytest.raises(BudgetExceededError):
        await agent.run(topic="Topic that exceeds tiny budget")
