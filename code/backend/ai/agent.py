"""Single LangGraph Research Agent + terminal CLI (`python -m ai.agent "topic"`).

Orchestrates the research tools (`search_papers`, `discover_literature`,
`get_collection`, `write_review`, `verify_citations`) in a deterministic
LangGraph StateGraph with `MemorySaver` checkpointing and approval pause/resume (M2).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Annotated, Literal, TypedDict
from uuid import UUID, uuid4

import httpx
from google.genai import Client as GenAIClient
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from config import get_settings
from engines.alrs import AlrsEngine
from engines.citations import AnalysisFinding
from engines.collections import InMemoryCollectionStore
from engines.embeddings import GeminiEmbeddingClient
from engines.openalex import AsyncTokenBucketRateLimiter, OpenAlexClient

from .tools import AgentToolRuntime, WriteReviewOutput
from .verification import VerificationReport, verify_review_citations


class ResearchAgentState(TypedDict):
    topic: str
    research_questions: list[str]
    seed_doi: str | None
    collection_id: str | None
    review_output: WriteReviewOutput | None
    verification_report: VerificationReport | None
    loaded_skills: list[str]
    messages: Annotated[list[BaseMessage], add_messages]


class AgentRunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    status: Literal["awaiting_approval", "completed", "cancelled"]
    topic: str
    seed_doi: str | None = None
    collection_id: str | None = None
    review_output: WriteReviewOutput | None = None
    verification_report: VerificationReport | None = None
    loaded_skills: list[str] = Field(default_factory=list)


class ResearchAgent:
    """LangGraph research agent backed by `AgentToolRuntime` and `MemorySaver`."""

    def __init__(
        self,
        runtime: AgentToolRuntime,
        checkpointer: MemorySaver | None = None,
    ) -> None:
        self.runtime = runtime
        self.checkpointer = checkpointer or MemorySaver()
        self.graph = self._build_graph()
        self._cancelled_threads: set[str] = set()

    def _build_graph(self) -> StateGraph:  # type: ignore[type-arg]
        builder: StateGraph = StateGraph(ResearchAgentState)  # type: ignore[type-arg]
        builder.add_node("select_seed", self._select_seed_node)
        builder.add_node("discover", self._discover_node)
        builder.add_node("synthesize_review", self._synthesize_review_node)
        builder.add_node("verify_citations", self._verify_citations_node)

        builder.add_edge(START, "select_seed")
        builder.add_edge("select_seed", "discover")
        builder.add_edge("discover", "synthesize_review")
        builder.add_edge("synthesize_review", "verify_citations")
        builder.add_edge("verify_citations", END)
        return builder

    async def _select_seed_node(self, state: ResearchAgentState) -> dict[str, object]:
        skill = self.runtime.load_skill("search-literature")
        skills = list(dict.fromkeys([*(state.get("loaded_skills") or []), skill.name]))
        if state.get("seed_doi"):
            return {
                "loaded_skills": skills,
                "messages": [
                    AIMessage(content=f"Using provided seed DOI: {state['seed_doi']}")
                ],
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
            "loaded_skills": skills,
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
        skill = self.runtime.load_skill("write-literature-review")
        skills = list(dict.fromkeys([*(state.get("loaded_skills") or []), skill.name]))
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
            "loaded_skills": skills,
            "messages": [AIMessage(content=review.markdown_review)],
        }

    async def _verify_citations_node(self, state: ResearchAgentState) -> dict[str, object]:
        skill = self.runtime.load_skill("verify-citations")
        skills = list(dict.fromkeys([*(state.get("loaded_skills") or []), skill.name]))
        collection_id = state["collection_id"]
        review = state["review_output"]
        assert collection_id is not None
        assert review is not None
        collection = self.runtime.collection_store.get(UUID(collection_id))
        report = verify_review_citations(collection, review)
        cleaned_review = review.model_copy(
            update={
                "markdown_review": report.cleaned_markdown,
                "cited_dois": report.verified_dois,
            }
        )
        return {
            "review_output": cleaned_review,
            "verification_report": report,
            "loaded_skills": skills,
            "messages": [
                AIMessage(
                    content=(
                        f"Verified {len(report.verified_dois)} DOI citations "
                        f"({len(report.unsupported_dois)} unsupported removed)."
                    )
                )
            ],
        }

    async def start_run(
        self,
        topic: str,
        seed_doi: str | None = None,
        research_questions: list[str] | None = None,
        require_approval: bool = False,
        thread_id: str | None = None,
    ) -> AgentRunStatus:
        tid = thread_id or str(uuid4())
        interrupts = ["discover"] if require_approval else []
        compiled = self.graph.compile(
            checkpointer=self.checkpointer,
            interrupt_before=interrupts,
        )
        initial_state: ResearchAgentState = {
            "topic": topic,
            "research_questions": research_questions or [topic],
            "seed_doi": seed_doi,
            "collection_id": None,
            "review_output": None,
            "verification_report": None,
            "loaded_skills": [],
            "messages": [HumanMessage(content=topic)],
        }
        config: RunnableConfig = {"configurable": {"thread_id": tid}}
        result_state = await compiled.ainvoke(initial_state, config=config)
        snapshot = await compiled.aget_state(config)
        if snapshot.next:
            return AgentRunStatus(
                thread_id=tid,
                status="awaiting_approval",
                topic=topic,
                seed_doi=result_state.get("seed_doi"),
                loaded_skills=list(result_state.get("loaded_skills") or []),
            )
        return AgentRunStatus(
            thread_id=tid,
            status="completed",
            topic=topic,
            seed_doi=result_state.get("seed_doi"),
            collection_id=result_state.get("collection_id"),
            review_output=result_state.get("review_output"),
            verification_report=result_state.get("verification_report"),
            loaded_skills=list(result_state.get("loaded_skills") or []),
        )

    async def resume_run(
        self,
        thread_id: str,
        approved: bool = True,
        override_seed_doi: str | None = None,
    ) -> AgentRunStatus:
        compiled = self.graph.compile(checkpointer=self.checkpointer)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await compiled.aget_state(config)
        values = dict(snapshot.values)
        topic = str(values.get("topic", ""))
        seed_doi = override_seed_doi or values.get("seed_doi")
        current_skills = values.get("loaded_skills")
        skills_list = list(current_skills) if isinstance(current_skills, list) else []
        if not approved:
            self._cancelled_threads.add(thread_id)
            return AgentRunStatus(
                thread_id=thread_id,
                status="cancelled",
                topic=topic,
                seed_doi=seed_doi if isinstance(seed_doi, str) else None,
                loaded_skills=skills_list,
            )
        if override_seed_doi:
            await compiled.aupdate_state(config, {"seed_doi": override_seed_doi})
        final_state = await compiled.ainvoke(None, config=config)
        return AgentRunStatus(
            thread_id=thread_id,
            status="completed",
            topic=topic,
            seed_doi=final_state.get("seed_doi"),
            collection_id=final_state.get("collection_id"),
            review_output=final_state.get("review_output"),
            verification_report=final_state.get("verification_report"),
            loaded_skills=list(final_state.get("loaded_skills") or []),
        )

    async def run(
        self,
        topic: str,
        seed_doi: str | None = None,
        research_questions: list[str] | None = None,
    ) -> WriteReviewOutput:
        status = await self.start_run(
            topic=topic,
            seed_doi=seed_doi,
            research_questions=research_questions,
            require_approval=False,
        )
        assert status.review_output is not None
        return status.review_output


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
