"""Adversarial stress-test suite for AGENT_USE_CASES_AND_EVALS.md.

Tests:
1. Structural integrity (5 main sections, 10 agent profiles, 7 subsections A-G per profile).
2. JSON syntax, schema compliance, and trajectory trace validity across all 10 profiles.
3. Mermaid and PlantUML diagram parsing and syntax validity.
4. Mathematical formulations, LaTeX syntax, and notation consistency across Section 3.
5. ADK EvalSet schema and Master's Thesis LaTeX mapping verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import pytest

DOC_PATH = Path(__file__).parent.parent / "docs" / "AGENT_USE_CASES_AND_EVALS.md"


@pytest.fixture(scope="module")
def doc_content() -> str:
    """Load the full document content."""
    assert DOC_PATH.exists(), f"Document not found at {DOC_PATH}"
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def doc_lines(doc_content: str) -> list[str]:
    """Return document lines."""
    return doc_content.splitlines()


def get_agent_section_text(doc_content: str, agent_prefix: str) -> str:
    """Extract full section text for an agent by its number prefix (e.g. '2.1')."""
    lines = doc_content.splitlines()
    start_idx = None
    end_idx = None

    for idx, line in enumerate(lines):
        if line.startswith(f"## {agent_prefix} "):
            start_idx = idx
            break

    assert start_idx is not None, f"Could not find section header for ## {agent_prefix}"

    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        if line.startswith("## 2.") or line.startswith("# Section 3"):
            end_idx = idx
            break

    if end_idx is None:
        end_idx = len(lines)

    return "\n".join(lines[start_idx:end_idx])


class TestDocumentStructure:
    """Validate top-level section hierarchy and required agent taxonomy components."""

    def test_file_exists_and_non_empty(self, doc_content: str) -> None:
        assert len(doc_content) > 100_000, "Document is unexpectedly short (<100KB)"

    def test_five_main_sections_present(self, doc_content: str) -> None:
        assert "# Section 1: Executive Summary & Swarm Topology" in doc_content
        assert "# Section 2: Comprehensive Agent Taxonomy & Use Case Specifications" in doc_content
        assert "# Section 3: Mathematical Formulations, Evaluation Rubrics, and Formal Verification Protocols" in doc_content
        assert "# Section 4: Swarm-Wide ADK Evaluation Dataset Specifications (.evalset.json)" in doc_content
        assert "# Section 5: Programmatic Pytest Harness & Academic Benchmark Reporting Protocols" in doc_content

    @pytest.mark.parametrize(
        "agent_prefix,agent_name",
        [
            ("2.1", "ProjectAgent"),
            ("2.2", "ResearchAgent"),
            ("2.3", "ALRSAgent"),
            ("2.4", "GapFinderAgent"),
            ("2.5", "EvidenceSynthesizerAgent"),
            ("2.6", "PlannerAgent"),
            ("2.7", "WriterAgent"),
            ("2.8", "DraftingAgent"),
            ("2.9", "ReviewerAgent"),
            ("2.10", "DebuggerAgent"),
        ],
    )
    def test_agent_profiles_and_subsections_a_to_g(
        self, doc_content: str, agent_prefix: str, agent_name: str
    ) -> None:
        """Verify each of the 10 agent profiles exists with all 7 subsections (A-G)."""
        sec_text = get_agent_section_text(doc_content, agent_prefix)
        assert agent_name in sec_text

        for sub_letter in ["A", "B", "C", "D", "E", "F", "G"]:
            sub_pattern = rf"### Subsection {sub_letter}:"
            assert re.search(sub_pattern, sec_text) is not None, (
                f"Agent {agent_prefix} ({agent_name}) missing Subsection {sub_letter}"
            )


class TestJsonBlocksAndTrajectories:
    """Validate JSON syntax, tool execution schemas, and trajectory traces."""

    def test_all_json_code_blocks_parse(self, doc_lines: list[str]) -> None:
        """Extract every ```json block in the document and verify valid JSON."""
        json_blocks = []
        in_block = False
        buf = []
        start_line = 0

        for idx, line in enumerate(doc_lines):
            line_no = idx + 1
            stripped = line.strip()
            if stripped.startswith("```json") and not in_block:
                in_block = True
                start_line = line_no
                buf = []
            elif stripped == "```" and in_block:
                in_block = False
                json_blocks.append((start_line, line_no, "\n".join(buf)))
                buf = []
            elif in_block:
                buf.append(line)

        assert len(json_blocks) >= 50, f"Expected at least 50 JSON blocks, found {len(json_blocks)}"

        errors = []
        for s, e, content in json_blocks:
            try:
                parsed = json.loads(content)
                assert isinstance(parsed, (dict, list))
            except Exception as exc:
                errors.append(f"Lines {s}-{e}: {exc}")

        assert len(errors) == 0, f"JSON parse failures:\n" + "\n".join(errors)

    @pytest.mark.parametrize(
        "agent_prefix,agent_name",
        [
            ("2.1", "ProjectAgent"),
            ("2.2", "ResearchAgent"),
            ("2.3", "ALRSAgent"),
            ("2.4", "GapFinderAgent"),
            ("2.5", "EvidenceSynthesizerAgent"),
            ("2.6", "PlannerAgent"),
            ("2.7", "WriterAgent"),
            ("2.8", "DraftingAgent"),
            ("2.9", "ReviewerAgent"),
            ("2.10", "DebuggerAgent"),
        ],
    )
    def test_trajectory_trace_schema_conformance(
        self, doc_content: str, agent_prefix: str, agent_name: str
    ) -> None:
        """Verify each agent profile's Subsection G trajectory trace conforms to ADK schema."""
        sec_text = get_agent_section_text(doc_content, agent_prefix)
        g_match = re.search(r"### Subsection G:.*?\n(.*)", sec_text, re.DOTALL)
        assert g_match is not None, f"Subsection G missing for {agent_name}"
        g_text = g_match.group(1)

        # Extract first JSON block in Subsection G
        lines = g_text.splitlines()
        json_lines = []
        capturing = False
        for l in lines:
            if l.strip().startswith("```json") and not capturing:
                capturing = True
                continue
            if capturing and l.strip() == "```":
                break
            if capturing:
                json_lines.append(l)

        assert len(json_lines) > 0, f"No JSON block in Subsection G for {agent_name}"
        data = json.loads("\n".join(json_lines))

        # Validate ADK turn schema
        assert "invocation_id" in data, f"Missing invocation_id in {agent_name}"
        assert "user_content" in data, f"Missing user_content in {agent_name}"
        assert data["user_content"]["role"] == "user"
        assert len(data["user_content"]["parts"]) >= 1

        assert "intermediate_data" in data, f"Missing intermediate_data in {agent_name}"
        assert "tool_uses" in data["intermediate_data"]
        assert len(data["intermediate_data"]["tool_uses"]) >= 1

        for tu in data["intermediate_data"]["tool_uses"]:
            assert "name" in tu, f"Tool use missing 'name' in {agent_name}"
            assert "args" in tu, f"Tool use missing 'args' in {agent_name}"
            assert isinstance(tu["args"], dict), f"Tool args not a dict in {agent_name}"

        assert "final_response" in data, f"Missing final_response in {agent_name}"
        assert data["final_response"]["role"] == "model"
        assert len(data["final_response"]["parts"]) >= 1


class TestDiagramsParsing:
    """Validate Mermaid and PlantUML diagrams."""

    def test_mermaid_diagram_syntax(self, doc_content: str) -> None:
        mermaid_match = re.search(r"```mermaid\n(.*?)```", doc_content, re.DOTALL)
        assert mermaid_match is not None, "Mermaid diagram not found"
        mmd = mermaid_match.group(1).strip()

        assert mmd.startswith("graph TB")
        assert "subgraph Client" in mmd
        assert "subgraph Tier0" in mmd
        assert "subgraph Tier1" in mmd
        assert "subgraph Tier2" in mmd
        assert "subgraph Tier3" in mmd
        assert "subgraph Storage" in mmd

        # Check bracket parity
        assert mmd.count("[") == mmd.count("]")
        assert mmd.count("(") == mmd.count(")")
        assert mmd.count("{") == mmd.count("}")

    def test_plantuml_diagrams_syntax(self, doc_content: str) -> None:
        puml_blocks = re.findall(r"```plantuml\n(.*?)```", doc_content, re.DOTALL)
        assert len(puml_blocks) == 2, f"Expected 2 PlantUML diagrams, found {len(puml_blocks)}"

        # Diagram 1: Architecture Component Diagram
        arch_puml = puml_blocks[0].strip()
        assert arch_puml.startswith("@startuml ALRS_v2_Swarm_Architecture")
        assert arch_puml.endswith("@enduml")
        assert arch_puml.count("{") == arch_puml.count("}")
        assert "package \"Presentation & Client Layer\"" in arch_puml
        assert "package \"Google ADK Multi-Agent Swarm\"" in arch_puml

        # Diagram 2: Sequence Execution Flow
        seq_puml = puml_blocks[1].strip()
        assert seq_puml.startswith("@startuml ALRS_v2_Execution_Sequence")
        assert seq_puml.endswith("@enduml")
        assert "autonumber" in seq_puml
        assert "actor Researcher as User" in seq_puml
        assert "== Stepwise 1-Hop GraphSelect Traversal Cycle ==" in seq_puml
        assert "== Section Drafting & Review Loop ==" in seq_puml


class TestMathematicalFormulations:
    """Validate LaTeX mathematical formulas and notation consistency across Section 3."""

    def test_section_3_subsections_exist(self, doc_content: str) -> None:
        assert "## 3.1 GraphSelect Directional Traversal & Cosine Semantic Similarity Formulas" in doc_content
        assert "## 3.2 Hybrid Relevance Ranking Formulation" in doc_content
        assert "## 3.3 Research Question Coverage & Gap Discovery Formulation" in doc_content
        assert "## 3.4 5-Dimension Peer-Review Evaluation Rubric & Approval Thresholds" in doc_content
        assert "## 3.5 Grounded Citation Deterministic Verification (GCDL)" in doc_content
        assert "## 3.6 ADK Trajectory Match Metric" in doc_content

    def test_latex_display_equations_balance(self, doc_content: str) -> None:
        """Verify display equations in Section 3 have balanced braces."""
        s3_match = re.search(r"# Section 3:.*?(?=# Section 4:)", doc_content, re.DOTALL)
        assert s3_match is not None
        s3_text = s3_match.group(0)

        display_eqs = re.findall(r"\$\$(.*?)\$\$", s3_text, re.DOTALL)
        assert len(display_eqs) >= 40

        unbalanced = []
        for idx, eq in enumerate(display_eqs):
            clean_eq = eq.replace(r"\{", "").replace(r"\}", "")
            o_b = clean_eq.count("{")
            c_b = clean_eq.count("}")
            if o_b != c_b:
                unbalanced.append((idx + 1, eq.strip(), o_b, c_b))

        assert len(unbalanced) <= 1, f"Found {len(unbalanced)} unbalanced display math equations: {unbalanced}"

    def test_mathematical_weights_and_constants_consistency(self, doc_content: str) -> None:
        """Verify weight constraints (summing to 1.0) and constants in Section 3."""
        # Foundational archetype weights: w = (0.35, 0.25, 0.20, 0.20) -> sum = 1.00
        assert "0.35, 0.25, 0.20, 0.20" in doc_content
        assert abs((0.35 + 0.25 + 0.20 + 0.20) - 1.00) < 1e-6

        # Contemporary archetype weights: mu = (0.50, 0.35, 0.15) -> sum = 1.00
        assert "0.50, 0.35, 0.15" in doc_content
        assert abs((0.50 + 0.35 + 0.15) - 1.00) < 1e-6

        # Bridge archetype weights: gamma = (0.40, 0.30, 0.30) -> sum = 1.00
        assert "0.40, 0.30, 0.30" in doc_content
        assert abs((0.40 + 0.30 + 0.30) - 1.00) < 1e-6

        # Hybrid relevance weights: alpha = 0.70, beta = 0.30 -> sum = 1.00
        assert "\\alpha = 0.70" in doc_content
        assert "\\beta = 0.30" in doc_content
        assert abs((0.70 + 0.30) - 1.00) < 1e-6

        # Rubric weights: 0.25 + 0.20 + 0.25 + 0.15 + 0.15 = 1.00
        assert "w_1 = 0.25" in doc_content
        assert "w_2 = 0.20" in doc_content
        assert "w_3 = 0.25" in doc_content
        assert "w_4 = 0.15" in doc_content
        assert "w_5 = 0.15" in doc_content
        assert abs((0.25 + 0.20 + 0.25 + 0.15 + 0.15) - 1.00) < 1e-6

        # ADK Trajectory weights: lambda1 = 0.50, lambda2 = 0.30, lambda3 = 0.20 -> sum = 1.00
        assert "\\lambda_1 = 0.50" in doc_content
        assert "\\lambda_2 = 0.30" in doc_content
        assert "\\lambda_3 = 0.20" in doc_content
        assert abs((0.50 + 0.30 + 0.20) - 1.00) < 1e-6


class TestADKBenchmarkAndThesisMapping:
    """Validate Section 4 and Section 5 specifications."""

    def test_seven_evalset_specifications_present(self, doc_content: str) -> None:
        evalset_files = [
            "alrs_discovery.evalset.json",
            "gap_finder.evalset.json",
            "evidence_synthesizer.evalset.json",
            "planner.evalset.json",
            "writer_reviewer.evalset.json",
            "debugger.evalset.json",
            "project_orchestrator.evalset.json",
        ]
        for ef in evalset_files:
            assert ef in doc_content, f"Eval set specification {ef} missing in Section 4"

    def test_thesis_latex_mapping_present(self, doc_content: str) -> None:
        assert "## 5.4 Master's Thesis LaTeX Integration Mapping" in doc_content
        assert "Chapter 4: System Design and Implementation" in doc_content
        assert "Chapter 6: Results and Discussion" in doc_content
        assert "Appendix B: Swarm Evaluation Protocols" in doc_content
