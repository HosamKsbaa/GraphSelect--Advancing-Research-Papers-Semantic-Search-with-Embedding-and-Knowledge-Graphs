"""Single LangGraph Research Agent + terminal CLI (`python -m ai.agent "topic"`).

Orchestrates the 4 research tools (`search_papers`, `discover_literature`,
`get_collection`, `write_review`) in a deterministic LangGraph StateGraph.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Annotated, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from config import get_settings
from engines.alrs import AlrsEngine
from engines.citations import AnalysisFinding
from engines.collections import InMemoryCollectionStore
from engines.embeddings import GeminiEmbeddingClient
from engines.openalex import AsyncTokenBucketRateLimiter, OpenAlexClient
from google.genai import Client as GenAIClient

from .tools import AgentToolRuntime, WriteReviewOutput


class ResearchAgentState(TypedDict):
    topic: str
    research_questions: list[str]
    seed_doi: str | None
    collection_id: str | None
    review_output: WriteReviewOutput | None
    messages: Annotated[list[BaseMessage], add_messages]


class ResearchAgent:
    """LangGraph research agent backed by `AgentToolRuntime`."""

    def __init__(self, runtime: AgentToolRuntime) -> None:
        self.runtime = runtime
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:  # type: ignore[type-arg]
        builder: StateGraph = StateGraph(ResearchAgentState)  # type: ignore[type-arg]
        builder.add_node("select_seed", self._select_seed_node)
        builder.add_node("discover", self._discover_node)
        builder.add_node("synthesize_review", self._synthesize_review_node)

        builder.add_edge(START, "select_seed")
        builder.add_edge("select_seed", "discover")
        builder.add_edge("discover", "synthesize_review")
        builder.add_edge("synthesize_review", END)
        return builder

    async def _select_seed_node(self, state: ResearchAgentState) -> dict[str, object]:
        if state.get("seed_doi"):
            return {
                "messages": [
                    AIMessage(content=f"Using provided seed DOI: {state['seed_doi']}")
                ]
            }
        search_res = await self.runtime.search_papers(state["topic"], limit=5)
        if not search_res.candidates:
            raise RuntimeError(f"No OpenAlex seed papers found for topic: {state['topic']}")
        chosen = next(
            (c for c in search_res.candidates if c.has_abstract),
            search_res.candidates[0],
        )
        return {
            "seed_doi": chosen.doi,
            "messages": [
                AIMessage(
                    content=f"Selected seed paper '{chosen.title}' (DOI: {chosen.doi})"
                )
            ],
        }

    async def _discover_node(self, state: ResearchAgentState) -> dict[str, object]:
        seed_doi = state["seed_doi"]
        assert seed_doi is not None
        questions = state.get("research_questions") or [state["topic"]]
        discovered = await self.runtime.discover_literature(
            seed_doi=seed_doi,
            research_questions=questions,
            max_depth=1,
            similarity_threshold=0.25,
        )
        return {
            "collection_id": discovered.collection_id,
            "research_questions": questions,
            "messages": [
                AIMessage(
                    content=(
                        f"Discovered {discovered.total_papers} papers in collection "
                        f"{discovered.collection_id}"
                    )
                )
            ],
        }

    async def _synthesize_review_node(self, state: ResearchAgentState) -> dict[str, object]:
        collection_id = state["collection_id"]
        assert collection_id is not None
        collection_ctx = self.runtime.get_collection(collection_id)
        questions = state.get("research_questions") or [state["topic"]]

        findings: list[AnalysisFinding] = []
        for question in questions:
            supporting_sources = []
            summaries: list[str] = []
            for paper_ctx in collection_ctx.papers[:3]:
                if paper_ctx.available_sources:
                    first_sentence = (
                        paper_ctx.available_sources[1]
                        if len(paper_ctx.available_sources) > 1
                        else paper_ctx.available_sources[0]
                    )
                    supporting_sources.append(first_sentence)
                    summaries.append(f"{paper_ctx.title} ({paper_ctx.year or 'n.d.'})")
            if supporting_sources:
                findings.append(
                    AnalysisFinding(
                        question=question,
                        finding=(
                            "Evidence from discovered literature highlights: "
                            + "; ".join(summaries)
                            + "."
                        ),
                        sources=supporting_sources,
                    )
                )

        review = self.runtime.write_review(collection_id=collection_id, findings=findings)
        return {
            "review_output": review,
            "messages": [AIMessage(content=review.markdown_review)],
        }

    async def run(
        self,
        topic: str,
        seed_doi: str | None = None,
        research_questions: list[str] | None = None,
    ) -> WriteReviewOutput:
        compiled = self.graph.compile()
        initial_state: ResearchAgentState = {
            "topic": topic,
            "research_questions": research_questions or [topic],
            "seed_doi": seed_doi,
            "collection_id": None,
            "review_output": None,
            "messages": [HumanMessage(content=topic)],
        }
        final_state = await compiled.ainvoke(initial_state)
        review_output = final_state["review_output"]
        assert isinstance(review_output, WriteReviewOutput)
        return review_output


async def run_cli(topic: str, seed_doi: str | None = None) -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        print(
            "Error: GEMINI_API_KEY is required to embed research questions.",
            file=sys.stderr,
        )
        return 1

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        openalex = OpenAlexClient(
            email=settings.openalex_email,
            rate_limiter=AsyncTokenBucketRateLimiter(rate=5.0, capacity=5.0),
            http_client=http_client,
        )
        genai_client = GenAIClient(api_key=settings.gemini_api_key)
        embeddings = GeminiEmbeddingClient(client=genai_client.aio)
        alrs_engine = AlrsEngine(openalex=openalex, embeddings=embeddings)
        runtime = AgentToolRuntime(
            openalex=openalex,
            alrs_engine=alrs_engine,
            collection_store=InMemoryCollectionStore(),
        )
        agent = ResearchAgent(runtime)
        review = await agent.run(topic=topic, seed_doi=seed_doi)
        print(review.markdown_review)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ALRS Research Agent in the terminal.")
    parser.add_argument("topic", help="Research topic or question to investigate")
    parser.add_argument("--seed-doi", default=None, help="Optional starting seed DOI")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_cli(args.topic, args.seed_doi)))


if __name__ == "__main__":
    main()
