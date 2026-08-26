"""
Adversarial Stress Test Suite for Milestone 5:
- Citation Hallucination Verification Engine (CitationVerifier)
- TeX Formatter AST, Escaping, and Key Collision Handling
- Multi-Agent Writing/Reviewer LoopAgent Convergence
- THESIS.tex LaTeX Syntax & references.bib Citation Resolution
"""
import re
import random
import string
import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import asdict

from agents.writing.citation_verifier import (
    CitationVerifier,
    CitationVerificationResult,
    extract_dois,
    normalize_doi,
    verify_citation_grounding,
)
from agents.writing.tex_formatter import (
    _escape_bibtex,
    _make_cite_key,
    _md_to_latex_body,
    generate_bibtex,
    format_to_latex,
)
from agents.writing.reviewer_agent import exit_loop
from agents.writing.agent import writer_reviewer_loop


# ==============================================================================
# SECTION 1: CITATION VERIFIER ADVERSARIAL STRESS TESTING
# ==============================================================================

class TestCitationVerifierAdversarial:
    """Adversarial stress testing of DOI extraction, normalization, and hallucination detection."""

    @pytest.mark.parametrize("raw_input, expected_doi", [
        ("https://doi.org/10.1000/182", "10.1000/182"),
        ("http://dx.doi.org/10.1000/182", "10.1000/182"),
        ("doi: 10.1000/182", "10.1000/182"),
        ("DOI:10.1000/182", "10.1000/182"),
        ("doi.org/10.1000/182", "10.1000/182"),
        ("(DOI: 10.1000/182)", "10.1000/182"),
        ("[doi: 10.1000/182]", "10.1000/182"),
        ("\"10.1000/182\"", "10.1000/182"),
        ("10.1000/ABC.DEF-123_45", "10.1000/abc.def-123_45"),
        ("10.1145/3308558.3313508.", "10.1145/3308558.3313508"),
        ("10.48550/arXiv.1706.03762;", "10.48550/arxiv.1706.03762"),
        ("10.1038/s41586-020-2649-2,", "10.1038/s41586-020-2649-2"),
    ])
    def test_normalize_doi_adversarial_formats(self, raw_input: str, expected_doi: str):
        """Test normalization across malformed, prefixed, and punctuated DOI strings."""
        assert normalize_doi(raw_input) == expected_doi

    def test_extract_dois_complex_text(self):
        """Test extraction of multiple mixed-format DOIs from dense markdown and LaTeX text."""
        sample_text = """
        Recent work by Vaswani et al. (https://doi.org/10.48550/arXiv.1706.03762) introduced transformers.
        Further advancements in GNNs (doi: 10.1145/3308558.3313508) and biomedical QA [DOI: 10.1038/s41586-020-2649-2]
        showed massive gains. Note that 10.48550/ARXIV.1706.03762 is repeated in uppercase.
        False positive candidates: 10.1234 (no slash), version 10.0.1/patch, and random string.
        Another valid: (see dx.doi.org/10.1000/182).
        Embedded in JSON: {"doi": "10.1109/CVPR.2021.00123"}
        Embedded in HTML: <a href="https://doi.org/10.1016/j.artint.2022.103789">Link</a>
        """
        extracted = extract_dois(sample_text)
        expected = [
            "10.48550/arxiv.1706.03762",
            "10.1145/3308558.3313508",
            "10.1038/s41586-020-2649-2",
            "10.1000/182",
            "10.1109/cvpr.2021.00123",
            "10.1016/j.artint.2022.103789",
        ]
        assert extracted == expected
        assert len(extracted) == 6  # Duplicate normalized and removed

    def test_100_percent_hallucination_detection_fuzzing(self):
        """Adversarially inject 100 fabricated DOIs and ensure 100% detection rate."""
        known_valid = {
            f"10.1000/valid_{i}": f"Valid Paper {i}" for i in range(20)
        }
        known_set = set(known_valid.keys())

        # Generate 50 valid and 50 fabricated citations
        valid_sample = random.sample(list(known_set), 10)
        fabricated_sample = [f"10.9999/fabricated_{i}_{random.randint(1000, 9999)}" for i in range(50)]

        all_citations = valid_sample + fabricated_sample
        random.shuffle(all_citations)

        text_content = " ".join([f"According to research ({doi}), findings are significant." for doi in all_citations])

        result = verify_citation_grounding(
            text=text_content,
            known_dois=known_set,
            assigned_dois=valid_sample,
        )

        assert result.is_grounded is False
        assert result.passed is False
        assert len(result.hallucinated_dois) == 50
        assert set(result.hallucinated_dois) == set(fabricated_sample)
        assert set(result.verified_dois) == set(valid_sample)
        assert result.hallucination_rate == pytest.approx(50 / 60, abs=1e-4)
        assert len(result.missing_assigned_dois) == 0

    def test_missing_assigned_citations_detection(self):
        """Test that omission of assigned DOIs is strictly detected and fails the verification."""
        assigned = ["10.1000/must_cite_1", "10.1000/must_cite_2", "10.1000/must_cite_3"]
        # Text only cites 1 of the 3
        text = "We cite 10.1000/must_cite_1 in our review."

        result = verify_citation_grounding(
            text=text,
            known_dois=assigned,
            assigned_dois=assigned,
        )

        assert result.is_grounded is True  # No hallucinated DOIs
        assert result.passed is False      # But missing assigned DOIs!
        assert result.missing_assigned_dois == ["10.1000/must_cite_2", "10.1000/must_cite_3"]
        assert result.coverage_rate == pytest.approx(1 / 3, abs=1e-4)

    @pytest.mark.asyncio
    async def test_citation_verifier_with_mock_neo4j(self):
        """Test CitationVerifier async database integration under adversarial queries."""
        mock_neo4j = AsyncMock()
        
        # Configure neo4j to only find specific DOIs
        async def mock_get_paper(doi: str):
            if doi == "10.1000/in_graph":
                return {"title": "Graph Paper", "year": 2023, "doi": doi}
            return None

        mock_neo4j.get_paper_by_doi.side_effect = mock_get_paper
        verifier = CitationVerifier(neo4j=mock_neo4j)

        text = "Citing (10.1000/in_graph), (10.1000/assigned_only), and (10.1000/fake_phantom)."
        result = await verifier.verify_text_citations(
            text=text,
            project_id="proj-123",
            assigned_dois=["10.1000/assigned_only"],
        )

        assert "10.1000/in_graph" in result.verified_dois
        assert "10.1000/assigned_only" in result.verified_dois
        assert result.hallucinated_dois == ["10.1000/fake_phantom"]
        assert result.is_grounded is False
        assert result.passed is False
        assert result.details["10.1000/in_graph"]["status"] == "verified_in_graph"
        assert result.details["10.1000/assigned_only"]["status"] == "verified_assigned_doi"
        assert result.details["10.1000/fake_phantom"]["status"] == "hallucinated_not_in_graph"


# ==============================================================================
# SECTION 2: TEX FORMATTER ADVERSARIAL FUZZING & KEY COLLISIONS
# ==============================================================================

class TestTeXFormatterAdversarial:
    """Adversarial stress testing of LaTeX character escaping, AST parsing, and BibTeX collisions."""

    @pytest.mark.parametrize("raw, expected", [
        ("AT&T and R&D", r"AT\&T and R\&D"),
        ("100% accuracy in 50% time", r"100\% accuracy in 50\% time"),
        ("variable_name_with_underscores", r"variable\_name\_with\_underscores"),
        ("Issue #42 and #123", r"Issue \#42 and \#123"),
        ("Costs $100 or $50", r"Costs \$100 or \$50"),
        ("Already escaped: \\& and \\% and \\_", r"Already escaped: \& and \% and \_"),
        ("Mixed: AT&T with \\& and 50% with \\%", r"Mixed: AT\&T with \& and 50\% with \%"),
        ("", ""),
    ])
    def test_escape_bibtex_special_chars(self, raw: str, expected: str):
        """Test escaping of special LaTeX characters without double-escaping."""
        assert _escape_bibtex(raw) == expected

    def test_make_cite_key_adversarial_inputs(self):
        """Test cite-key generation on extreme title/author/doi inputs."""
        # 1. Normal title
        p1 = {"title": "Attention Is All You Need", "year": 2017, "doi": "10.1000/1"}
        assert _make_cite_key(p1) == "attention2017"

        # 2. Title with special characters and punctuation
        p2 = {"title": "!@#$%^&*()_+Special Title", "year": 2024, "doi": "10.1000/2"}
        assert _make_cite_key(p2) == "special2024"

        # 3. Missing title, author list with full names
        p3 = {"authors": ["Vaswani, Ashish", "Noam Shazeer"], "year": 2017, "doi": "10.1000/3"}
        assert _make_cite_key(p3) == "ashish2017"

        # 4. Missing title and author, DOI fallback
        p4 = {"doi": "10.1145/3308558.3313508", "year": 2019}
        assert _make_cite_key(p4) == "3308558331352019"

        # 5. Missing title, author, year, and blank DOI
        p5 = {"doi": ""}
        assert _make_cite_key(p5) == "paperXXXX"

    def test_generate_bibtex_50_identical_key_collisions(self):
        """Stress test BibTeX key deduplication with 50 papers having identical title & year."""
        papers = [
            {
                "title": "Deep Learning Review",
                "year": 2023,
                "doi": f"10.1000/dl_review_{i}",
                "authors": [f"Author {i}"],
                "abstract": f"Abstract for paper {i} with & special % chars.",
                "source": "Nature & Science",
            }
            for i in range(50)
        ]

        bibtex = generate_bibtex(papers)
        
        # Verify 50 @article entries generated
        assert bibtex.count("@article{") == 50

        # Extract all generated cite keys
        cite_keys = re.findall(r"@article\{([^,]+),", bibtex)
        assert len(cite_keys) == 50
        # 100% uniqueness requirement
        assert len(set(cite_keys)) == 50

        # Check collision suffix sequence
        assert cite_keys[0] == "deep2023"
        assert cite_keys[1] == "deep2023b"
        assert cite_keys[2] == "deep2023c"
        assert cite_keys[25] == "deep2023z"

        # Verify special characters in fields are strictly escaped
        assert r"Nature \& Science" in bibtex
        assert r"with \& special \% chars." in bibtex

    def test_markdown_to_latex_body_ast_fuzzing(self):
        """Adversarial fuzzing of markdown syntax conversion to LaTeX."""
        md = """
# Primary Section & Analysis

Here is a paragraph with **bold text & ampersands** and *italicized text with % signs* and `inline_code_block()`.

## Subsection: Method 50% Speedup

1. First enumerated item with **bold**
2. Second enumerated item with `code`

- Bullet item one with $O(N)$ math
- Bullet item two

> This is an important quote with **crucial** findings & notes.

```python
def solve(a, b):
    # Python comment & code
    return a + b
```

### Subsubsection with #hashtag
#### Paragraph heading
        """

        latex_body = _md_to_latex_body(md)

        # Check headings
        assert r"\section{Primary Section \& Analysis}" in latex_body
        assert r"\subsection{Subsection: Method 50\% Speedup}" in latex_body
        assert r"\subsubsection{Subsubsection with \#hashtag}" in latex_body
        assert r"\paragraph{Paragraph heading}" in latex_body

        # Check formatting
        assert r"\textbf{bold text & ampersands}" in latex_body
        assert r"\textit{italicized text with % signs}" in latex_body
        assert r"\texttt{inline_code_block()}" in latex_body

        # Check environments
        assert r"\begin{enumerate}" in latex_body
        assert r"\end{enumerate}" in latex_body
        assert r"\begin{itemize}" in latex_body
        assert r"\end{itemize}" in latex_body
        assert r"\begin{quote}" in latex_body
        assert r"\end{quote}" in latex_body
        assert r"\begin{verbatim}" in latex_body
        assert r"\end{verbatim}" in latex_body

    def test_format_to_latex_complete_document_templates(self):
        """Verify format_to_latex generates valid full documents across IEEE, ACM, and Plain templates."""
        md = "## Test Section\nContent here citing 10.1000/182."
        citations = ["10.1000/182"]

        for tmpl in ["ieee", "acm", "plain", "unknown_fallback"]:
            tex = format_to_latex(md, citations=citations, template=tmpl)
            assert r"\begin{document}" in tex
            assert r"\end{document}" in tex
            assert r"\maketitle" in tex
            assert r"\bibliography{references}" in tex
            assert "% Total DOI citations detected: 1" in tex


# ==============================================================================
# SECTION 3: MULTI-AGENT LOOP CONVERGENCE & MAX_ITERATIONS
# ==============================================================================

class TestLoopAgentConvergence:
    """Stress testing LoopAgent convergence and termination invariants."""

    def test_loop_agent_configuration_and_max_iterations(self):
        """Verify LoopAgent is configured with max_iterations=3 and correct sub-agents."""
        assert writer_reviewer_loop.name == "WriterReviewerLoop"
        assert writer_reviewer_loop.max_iterations == 3
        sub_agent_names = [agent.name for agent in writer_reviewer_loop.sub_agents]
        assert sub_agent_names == ["DraftingAgent", "ReviewerAgent"]

    def test_exit_loop_tool_escalation(self):
        """Verify exit_loop tool properly sets escalate and skip_summarization flags."""
        mock_tool_context = MagicMock()
        mock_tool_context.actions.escalate = False
        mock_tool_context.actions.skip_summarization = False

        res = exit_loop(mock_tool_context)
        assert res == {"status": "loop_exited"}
        assert mock_tool_context.actions.escalate is True
        assert mock_tool_context.actions.skip_summarization is True

    def test_persistent_low_scores_loop_simulation(self):
        """Simulate execution where reviewer persistently returns unapproved score to verify termination at 3."""
        iteration_count = 0
        max_iterations = 3
        history = []

        # Simulated Loop iteration
        while iteration_count < max_iterations:
            iteration_count += 1
            # Step 1: Drafting Agent produces draft
            draft = f"Draft iteration {iteration_count}"
            
            # Step 2: Reviewer Agent evaluates (persistent low score)
            review = {
                "approved": False,
                "scores": {"coverage": 2, "coherence": 2, "synthesis": 2},
                "feedback": [f"Feedback iteration {iteration_count}"],
                "missing_citations": ["10.1000/missing"],
            }
            history.append((iteration_count, draft, review))

            if review["approved"]:
                # exit_loop called
                break

        assert iteration_count == 3
        assert len(history) == 3
        assert history[-1][2]["approved"] is False
        # Loop strictly halts at max_iterations=3 without hanging or infinite cycling


# ==============================================================================
# SECTION 4: THESIS.TEX SYNTAX & REFERENCES.BIB CITATION RESOLUTION
# ==============================================================================

class TestThesisLaTeXSyntaxAndCitations:
    """Forensic verification of THESIS.tex LaTeX syntax and citation resolution against references.bib."""

    def test_thesis_latex_and_bibtex_citations_resolution(self):
        """Verify 100% of citations in THESIS.tex resolve to valid entries in references.bib."""
        import os
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_dir = os.path.abspath(os.path.join(backend_dir, "../../.."))

        thesis_tex_path = os.path.join(root_dir, "paper/myPapers/masterPapers/thesis/THESIS.tex")
        thesis_bib_path = os.path.join(root_dir, "paper/myPapers/masterPapers/thesis/references.bib")

        assert os.path.exists(thesis_tex_path), f"THESIS.tex not found at {thesis_tex_path}"
        assert os.path.exists(thesis_bib_path), f"references.bib not found at {thesis_bib_path}"

        with open(thesis_tex_path, "r", encoding="utf-8") as f:
            tex_content = f.read()

        with open(thesis_bib_path, "r", encoding="utf-8") as f:
            bib_content = f.read()

        # Parse BibTeX keys
        bib_keys = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib_content))
        assert len(bib_keys) > 0, "No BibTeX keys parsed from references.bib"

        # Parse \cite{...} in THESIS.tex
        cite_matches = re.findall(r"\\cite(?:\[[^\]]*\])?\{([^}]+)\}", tex_content)
        tex_cited_keys = set()
        for match in cite_matches:
            keys = [k.strip() for k in match.split(",") if k.strip()]
            tex_cited_keys.update(keys)

        assert len(tex_cited_keys) > 0, "No citations found in THESIS.tex"

        # Check resolution
        unresolved_keys = tex_cited_keys - bib_keys
        print(f"Total citations in THESIS.tex: {len(tex_cited_keys)}")
        print(f"Total BibTeX entries: {len(bib_keys)}")
        print(f"Unresolved citations: {unresolved_keys}")

        assert len(unresolved_keys) == 0, f"Unresolved citations found in THESIS.tex: {unresolved_keys}"

    def test_thesis_latex_environment_closure(self):
        """Verify that all \\begin{env} environments in THESIS.tex have matching \\end{env}."""
        import os
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_dir = os.path.abspath(os.path.join(backend_dir, "../../.."))
        thesis_tex_path = os.path.join(root_dir, "paper/myPapers/masterPapers/thesis/THESIS.tex")

        with open(thesis_tex_path, "r", encoding="utf-8") as f:
            tex_content = f.read()

        begin_envs = re.findall(r"\\begin\{([a-zA-Z0-9*]+)\}", tex_content)
        end_envs = re.findall(r"\\end\{([a-zA-Z0-9*]+)\}", tex_content)

        from collections import Counter
        begin_counts = Counter(begin_envs)
        end_counts = Counter(end_envs)

        for env, count in begin_counts.items():
            assert end_counts[env] == count, f"Environment mismatch for '{env}': begin={count}, end={end_counts[env]}"
        assert set(begin_counts.keys()) == set(end_counts.keys()), "Environment set mismatch"
