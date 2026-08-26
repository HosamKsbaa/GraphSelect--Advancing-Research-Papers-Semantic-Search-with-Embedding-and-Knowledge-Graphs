"""Unit and integration tests for the deterministic LaTeX and BibTeX formatting engine.

Covers:
    - Cite-key generation and collision-free uniqueness (e.g., vaswani2017, vaswani2017a)
    - Strict LaTeX character escaping (&, %, _, #, $)
    - BibTeX generation (generate_bibtex) across multiple paper configurations
    - Markdown-to-LaTeX body conversion (_md_to_latex_body)
    - Template generation for IEEEtran, ACM, and plain article (format_to_latex)
"""
from __future__ import annotations

from pathlib import Path
import pytest

from agents.writing.tex_formatter import (
    _escape_bibtex,
    _make_cite_key,
    _md_to_latex_body,
    format_to_latex,
    generate_bibtex,
)


# ============================================================================
# Cite-Key Generation Tests
# ============================================================================

def test_make_cite_key_from_title():
    """Test cite key generation from paper title and publication year."""
    paper = {"title": "Attention Is All You Need", "year": 2017, "doi": "10.1000/1"}
    assert _make_cite_key(paper) == "attention2017"


def test_make_cite_key_from_authors_fallback():
    """Test cite key generation from authors when title is empty."""
    paper = {"title": "", "authors": ["Ashish Vaswani"], "year": 2017, "doi": "10.1000/1"}
    assert _make_cite_key(paper) == "vaswani2017"


def test_make_cite_key_from_doi_fallback():
    """Test cite key generation from DOI suffix when title and authors are missing."""
    paper = {"doi": "10.1000/transformer-model", "year": 2023}
    assert _make_cite_key(paper) == "transformerm2023"


def test_make_cite_key_missing_year():
    """Test cite key generation when year is missing defaults to XXXX."""
    paper = {"title": "Deep Residual Learning", "doi": "10.1000/he2016"}
    assert _make_cite_key(paper) == "deepXXXX"


# ============================================================================
# Collision-Free BibTeX Generation Tests
# ============================================================================

def test_generate_bibtex_collision_free_keys():
    """Test duplicate cite keys produce collision-free suffixes (vaswani2017, vaswani2017a, vaswani2017b)."""
    papers = [
        {"doi": "10.1000/v1", "title": "Vaswani Model Architecture", "year": 2017, "authors": ["A. Vaswani"]},
        {"doi": "10.1000/v2", "title": "Vaswani Scaled Attention", "year": 2017, "authors": ["A. Vaswani"]},
        {"doi": "10.1000/v3", "title": "Vaswani Positional Encoding", "year": 2017, "authors": ["A. Vaswani"]},
    ]
    bibtex = generate_bibtex(papers)

    assert "@article{vaswani2017," in bibtex
    assert "@article{vaswani2017b," in bibtex
    assert "@article{vaswani2017c," in bibtex


def test_generate_bibtex_empty_list():
    """Test generate_bibtex handles empty input list."""
    assert generate_bibtex([]) == "% No papers to export.\n"


def test_generate_bibtex_author_formatting():
    """Test author list formatted as 'Author1 and Author2 and Author3'."""
    papers = [
        {
            "doi": "10.1000/multi-author",
            "title": "Collaborative Research",
            "year": 2024,
            "authors": ["Alice Smith", "Bob Jones", "Charlie Brown"],
        }
    ]
    bibtex = generate_bibtex(papers)
    assert "author    = {Alice Smith and Bob Jones and Charlie Brown}," in bibtex


# ============================================================================
# Strict Character Escaping Tests
# ============================================================================

def test_escape_bibtex_special_characters():
    """Test strict escaping of &, %, _, #, $ characters."""
    raw = "Analysis & Results: 95% accuracy on dataset_v2 for project #1 costing $100."
    escaped = _escape_bibtex(raw)

    assert r"\&" in escaped
    assert r"\%" in escaped
    assert r"\_" in escaped
    assert r"\#" in escaped
    assert r"\$" in escaped
    assert "&" not in escaped.replace(r"\&", "")
    assert "%" not in escaped.replace(r"\%", "")
    assert "_" not in escaped.replace(r"\_", "")
    assert "#" not in escaped.replace(r"\#", "")
    assert "$" not in escaped.replace(r"\$", "")


def test_escape_bibtex_avoids_double_escaping():
    """Test that already escaped characters are not double-escaped."""
    already_escaped = r"Cost is \$50 and rate is 90\% with item\_1 \& item\_2 \#3"
    result = _escape_bibtex(already_escaped)

    assert r"\\$" not in result
    assert r"\\%" not in result
    assert r"\\_" not in result
    assert r"\\&" not in result
    assert r"\\#" not in result


# ============================================================================
# Markdown to LaTeX Body Conversion Tests
# ============================================================================

def test_md_to_latex_body_headings():
    """Test markdown headings converted to section, subsection, subsubsection, paragraph."""
    md = "# Section One\n\n## Sub Section\n\n### Sub Sub Section\n\n#### Paragraph Head"
    latex = _md_to_latex_body(md)

    assert r"\section{Section One}" in latex
    assert r"\subsection{Sub Section}" in latex
    assert r"\subsubsection{Sub Sub Section}" in latex
    assert r"\paragraph{Paragraph Head}" in latex


def test_md_to_latex_body_inline_styles():
    """Test bold, italic, and inline code formatting."""
    md = "This is **bold text**, this is *italic text*, and `inline_code()`."
    latex = _md_to_latex_body(md)

    assert r"\textbf{bold text}" in latex
    assert r"\textit{italic text}" in latex
    assert r"\texttt{inline_code()}" in latex


def test_md_to_latex_body_lists():
    """Test itemize and enumerate environment generation."""
    md_bullet = "- Item Alpha\n- Item Beta\n- Item Gamma"
    latex_bullet = _md_to_latex_body(md_bullet)

    assert r"\begin{itemize}" in latex_bullet
    assert r"\item Item Alpha" in latex_bullet
    assert r"\item Item Beta" in latex_bullet
    assert r"\end{itemize}" in latex_bullet

    md_enum = "1. First step\n2. Second step\n3. Third step"
    latex_enum = _md_to_latex_body(md_enum)

    assert r"\begin{enumerate}" in latex_enum
    assert r"\item First step" in latex_enum
    assert r"\item Second step" in latex_enum
    assert r"\end{enumerate}" in latex_enum


def test_md_to_latex_body_code_blocks_and_quotes():
    """Test verbatim code blocks and blockquotes."""
    md = "```python\nprint('hello')\n```\n\n> Key insight from research."
    latex = _md_to_latex_body(md)

    assert r"\begin{verbatim}" in latex
    assert "print('hello')" in latex
    assert r"\end{verbatim}" in latex
    assert r"\begin{quote}" in latex
    assert "Key insight from research." in latex
    assert r"\end{quote}" in latex


# ============================================================================
# LaTeX Template Formatting Tests
# ============================================================================

def test_format_to_latex_ieee_template():
    """Test complete IEEEtran document formatting."""
    md = "## Introduction\n\nGraph Neural Networks are powerful \\cite{scarselli2009}."
    latex = format_to_latex(md, citations=["10.1000/1"], template="ieee")

    assert r"\documentclass[conference]{IEEEtran}" in latex
    assert r"\usepackage{cite}" in latex
    assert r"\title{Literature Review}" in latex
    assert r"\begin{document}" in latex
    assert r"\maketitle" in latex
    assert r"\subsection{Introduction}" in latex
    assert r"\bibliographystyle{IEEEtran}" in latex
    assert r"\bibliography{references}" in latex
    assert r"\end{document}" in latex


def test_format_to_latex_acm_template():
    """Test ACM acmart document formatting."""
    md = "## Methodology\n\nSystem architecture."
    latex = format_to_latex(md, citations=[], template="acm")

    assert r"\documentclass[sigconf]{acmart}" in latex
    assert r"\bibliographystyle{plain}" in latex
    assert r"\bibliography{references}" in latex


def test_format_to_latex_plain_template():
    """Test plain article document formatting."""
    md = "## Analysis\n\nEvaluation findings."
    latex = format_to_latex(md, citations=[], template="plain")

    assert r"\documentclass[12pt]{article}" in latex
    assert r"\usepackage{natbib}" in latex
    assert r"\bibliographystyle{plain}" in latex


def test_format_to_latex_fallback_to_ieee():
    """Test unknown template parameter falls back safely to IEEEtran."""
    md = "# Overview"
    latex = format_to_latex(md, citations=[], template="custom_unsupported")

    assert r"\documentclass[conference]{IEEEtran}" in latex


def test_pdflatex_compilation_all_templates(tmp_path: Path):
    """Test that generated LaTeX documents for plain, ieee, and acm compile to valid PDFs with pdflatex."""
    import shutil
    import subprocess

    pdflatex_bin = shutil.which("pdflatex")
    if not pdflatex_bin:
        pytest.skip("pdflatex is not installed on system")

    backend_root = Path(__file__).resolve().parent.parent
    templates_dir = backend_root / "templates" / "latex"

    for tmpl in ["plain", "ieee", "acm"]:
        md = f"# Section One\n\nThis is testing the {tmpl} template compilation."
        latex_code = format_to_latex(md, citations=[], template=tmpl)

        work_dir = tmp_path / f"compile_{tmpl}"
        work_dir.mkdir(parents=True)

        tex_file = work_dir / "doc.tex"
        tex_file.write_text(latex_code, encoding="utf-8")
        (work_dir / "references.bib").write_text("", encoding="utf-8")

        # Copy class files
        if templates_dir.exists():
            for item in templates_dir.glob("*"):
                if item.is_file():
                    shutil.copy(item, work_dir)

        proc = subprocess.run(
            [pdflatex_bin, "-interaction=nonstopmode", "-file-line-error", "doc.tex"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )

        pdf_out = work_dir / "doc.pdf"
        assert pdf_out.exists(), f"pdflatex failed for {tmpl}:\n{proc.stdout[-500:]}"
        assert pdf_out.stat().st_size > 0

