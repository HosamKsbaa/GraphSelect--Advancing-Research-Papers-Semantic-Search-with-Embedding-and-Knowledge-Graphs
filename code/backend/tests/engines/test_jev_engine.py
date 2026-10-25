"""Contract and mathematical tests for `engines.jev`.

Ported from archive commit 865cd08 (`tests/test_jev_client.py`,
`tests/test_jev_normalization_stress.py`, and `tests/test_epistemic_graphselect.py`).
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from engines.jev import (
    DEFAULT_PROBABILITY_TOLERANCE,
    IEEE_754_EPSILON,
    JEV_ENDPOINT,
    EpistemicGraphSelectConfig,
    JevChoiceAnswer,
    JevChoiceQuestion,
    JevClientSettings,
    JevDecisionClient,
    JevError,
    calculate_bridge_balance,
    calculate_dimension_score,
    calculate_expected_dimension_utility,
    calculate_normalized_entropy,
    evaluate_candidates_with_jev,
    normalize_probability_distribution,
    should_prune_candidate_subtree,
)
from engines.papers import Paper

TEST_KEY = "test-secret-never-log"


def configured_settings(**values: object) -> JevClientSettings:
    return JevClientSettings.model_validate(
        {"typesafe_api_key": SecretStr(TEST_KEY), "jev_enabled": True, **values}
    )


def sample_question() -> dict[str, JevChoiceQuestion]:
    return {
        "relationship": JevChoiceQuestion(
            instructions="Classify only the supplied citation passage.",
            criteria={
                "uses": "Explicitly uses the cited method.",
                "unclear": "Evidence is insufficient.",
            },
        )
    }


def valid_response() -> dict[str, JsonValue]:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "relationship": {
                "type": "choice",
                "choice": "uses",
                "probabilities": {"uses": 0.9, "unclear": 0.1},
                "confidence": 0.7,
            }
        },
        "usage": {"input_tokens": 41, "output_tokens": 15},
    }


def replace_field(document: dict[str, JsonValue], path: list[str], value: JsonValue) -> None:
    container = document
    for name in path[:-1]:
        child = container[name]
        assert isinstance(child, dict)
        container = child
    container[path[-1]] = value


def test_upper_and_lower_probability_boundary_sweeps() -> None:
    tau = DEFAULT_PROBABILITY_TOLERANCE
    eps = IEEE_754_EPSILON
    base_split = 0.5

    for delta in (-1e-5, -1e-8, -1e-11, -1e-12, 0.0):
        upper_sum = 1.0 + tau + eps + delta
        dist = {"choice_a": base_split, "choice_b": upper_sum - base_split}
        normalized = normalize_probability_distribution(dist)
        assert abs(sum(normalized.values()) - 1.0) < 1e-12
        assert max(normalized, key=lambda k: normalized[k]) == max(dist, key=lambda k: dist[k])

        lower_sum = 1.0 - (tau + eps) - delta
        dist_low = {"choice_a": base_split, "choice_b": lower_sum - base_split}
        normalized_low = normalize_probability_distribution(dist_low)
        assert abs(sum(normalized_low.values()) - 1.0) < 1e-12

    for exceeding in (1e-8, 1e-5, 1e-3, 0.01):
        with pytest.raises(ValueError, match="Probability drift exceeded"):
            normalize_probability_distribution(
                {"a": base_split, "b": 1.0 + tau + eps + exceeding - base_split}
            )
        with pytest.raises(ValueError, match="Probability drift exceeded"):
            normalize_probability_distribution(
                {"a": base_split, "b": 1.0 - (tau + eps) - exceeding - base_split}
            )


def test_negative_underflow_clamping_and_bounds() -> None:
    clamped = normalize_probability_distribution({"a": 1.000005, "b": -5e-6})
    assert clamped["b"] == 0.0
    assert abs(clamped["a"] - 1.0) < 1e-12

    with pytest.raises(ValueError, match="Negative probability"):
        normalize_probability_distribution({"a": 1.0001, "b": -1.1e-5})


@pytest.mark.anyio
async def test_client_posts_typed_request_and_validates_measured_result() -> None:
    requests: list[httpx.Request] = []

    def external_jev(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=valid_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(external_jev)) as http:
        result = await JevDecisionClient(configured_settings(), http).decide(
            {"passage": "We use Paper A's method."},
            sample_question(),
            function="research_lineage",
        )
    request = requests[0]
    assert len(requests) == 1 and str(request.url) == JEV_ENDPOINT and request.method == "POST"
    assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
    payload = json.loads(request.content)
    assert payload == {
        "model": "jev-1.13.0",
        "state": {"passage": "We use Paper A's method."},
        "questions": {"relationship": sample_question()["relationship"].model_dump()},
    }
    assert TEST_KEY not in request.content.decode()
    assert result.answers["relationship"].choice == "uses"
    assert result.answers["relationship"].probabilities == {"uses": 0.9, "unclear": 0.1}
    assert result.usage.input_tokens == 41 and result.usage.output_tokens == 15
    assert result.input_hash == hashlib.sha256(request.content).hexdigest()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "values",
    [{"typesafe_api_key": None}, {"typesafe_api_key": SecretStr(" ")}, {"jev_enabled": False}],
)
async def test_unconfigured_or_disabled_client_never_sends_http(
    values: dict[str, object],
) -> None:
    def unexpected_http(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unconfigured Jev must not send a request.")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as http:
        client = JevDecisionClient(configured_settings(**values), http)
        assert not client.configured
        with pytest.raises(JevError) as failure:
            await client.decide("Passage", sample_question())
    assert failure.value.code == "jev_not_configured"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path,value",
    [
        (["model"], "jev-latest"),
        (["answers"], {}),
        (["answers", "relationship", "choice"], "invented"),
        (["answers", "relationship", "choice"], "unclear"),
        (["answers", "relationship", "probabilities"], {"uses": 1}),
        (["answers", "relationship", "probabilities"], {"uses": 0.9, "unclear": 0.9}),
        (["answers", "relationship", "confidence"], 1.1),
        (["usage", "output_tokens"], -1),
    ],
)
async def test_invalid_provider_answers_never_become_success(
    path: list[str], value: JsonValue
) -> None:
    document = valid_response()
    replace_field(document, path, value)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(document).encode())
        )
    ) as http:
        with pytest.raises(JevError) as failure:
            await JevDecisionClient(configured_settings(), http).decide(
                "Passage", sample_question()
            )
    assert failure.value.code == "invalid_jev_response"
    assert TEST_KEY not in str(failure.value)


def test_epistemic_entropy_utility_and_subtree_pruning_math() -> None:
    # Uniform 4-choice distribution has normalized Shannon entropy 1.0
    uniform = {
        "direct_evidence": 0.25,
        "methodological_foundation": 0.25,
        "background_context": 0.25,
        "unrelated": 0.25,
    }
    assert abs(calculate_normalized_entropy(uniform) - 1.0) < 1e-9

    # Deterministic 1-choice mass has normalized Shannon entropy 0.0
    certain = {
        "direct_evidence": 1.0,
        "methodological_foundation": 0.0,
        "background_context": 0.0,
        "unrelated": 0.0,
    }
    assert calculate_normalized_entropy(certain) == 0.0
    assert calculate_expected_dimension_utility("alignment", certain) == 1.0

    ans = JevChoiceAnswer(
        type="choice",
        choice="direct_evidence",
        probabilities=certain,
        confidence=0.90,
    )
    dim_score = calculate_dimension_score("alignment", ans, entropy_penalty_weight=0.50)
    assert abs(dim_score.discounted_score - 0.90) < 1e-9

    # Subtree pruning triggers only on high-confidence exclusion
    exclude_high = JevChoiceAnswer(
        type="choice",
        choice="exclude",
        probabilities={"include": 0.05, "unclear": 0.05, "exclude": 0.90},
        confidence=0.85,
    )
    assert should_prune_candidate_subtree(exclude_high, prune_confidence_threshold=0.70) is True

    exclude_low = JevChoiceAnswer(
        type="choice",
        choice="exclude",
        probabilities={"include": 0.20, "unclear": 0.30, "exclude": 0.50},
        confidence=0.60,
    )
    assert should_prune_candidate_subtree(exclude_low, prune_confidence_threshold=0.70) is False
    assert abs(calculate_bridge_balance([0.8, 0.8]) - 1.0) < 1e-6


@pytest.mark.anyio
async def test_evaluate_candidates_with_jev_builds_3d_assessments() -> None:
    paper = Paper(
        doi="10.48550/arxiv.1706.03762",
        title="Attention Is All You Need",
        abstract="We propose the Transformer based solely on attention mechanisms.",
        year=2017,
    )

    def mock_jev(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    "p0_alignment": {
                        "type": "choice",
                        "choice": "direct_evidence",
                        "probabilities": {
                            "direct_evidence": 0.85,
                            "methodological_foundation": 0.10,
                            "background_context": 0.05,
                            "unrelated": 0.0,
                        },
                        "confidence": 0.9,
                    },
                    "p0_citation_role": {
                        "type": "choice",
                        "choice": "foundational_or_extension",
                        "probabilities": {
                            "foundational_or_extension": 0.90,
                            "comparative_benchmark": 0.05,
                            "cross_domain_bridge": 0.05,
                            "incidental_reference": 0.0,
                        },
                        "confidence": 0.9,
                    },
                    "p0_screening": {
                        "type": "choice",
                        "choice": "include",
                        "probabilities": {"include": 0.92, "unclear": 0.08, "exclude": 0.0},
                        "confidence": 0.95,
                    },
                },
                "usage": {"input_tokens": 120, "output_tokens": 45},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_jev)) as http:
        client = JevDecisionClient(configured_settings(), http)
        report = await evaluate_candidates_with_jev(
            [paper],
            ["How does self-attention replace recurrence?"],
            {paper.paper_key: 0.88},
            client,
            EpistemicGraphSelectConfig(),
        )

    assert report.completed_calls == 1
    assert paper.paper_key in report.assessments
    assessment = report.assessments[paper.paper_key]
    assert assessment.screening_label == "include"
    assert assessment.prune_subtree is False
    assert assessment.composite_epistemic_score > 0.7
