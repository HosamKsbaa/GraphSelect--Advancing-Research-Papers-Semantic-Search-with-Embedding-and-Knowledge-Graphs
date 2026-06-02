"""TeX formatting utilities for the writing pipeline.

Pure-Python, deterministic functions that convert Markdown drafts
to LaTeX and generate BibTeX entries from paper metadata.  These
are used by the export tools, not as ADK tools directly.

Functions:
    - format_to_latex: Markdown → LaTeX with template wrapping
    - generate_bibtex: Paper dicts → .bib file content
"""
from __future__ import annotations

import re
from typing import Any


# ------------------------------------------------------------------
# BibTeX key generation
# ------------------------------------------------------------------

def _make_cite_key(paper: dict[str, Any]) -> str:
    """Generate a BibTeX cite key from a paper dict.

    Uses the first word of the title + year, falling back to a
    DOI-based slug if title is missing.

    Args:
        paper: Dict with at least 'doi' and optionally 'title', 'year'.

    Returns:
        A string suitable for use as a BibTeX cite key.
    """
    title: str = paper.get("title") or ""
    year: int | None = paper.get("year")
    doi: str = paper.get("doi", "unknown")

    if title:
        first_word = re.sub(r"[^a-zA-Z]", "", title.split()[0]) if title.split() else "unknown"
    else:
        # Use DOI suffix as fallback
        first_word = re.sub(r"[^a-zA-Z0-9]", "", doi.split("/")[-1])[:12]

    year_str = str(year) if year else "XXXX"
    return f"{first_word.lower()}{year_str}"


def _escape_bibtex(text: str) -> str:
    """Escape special LaTeX/BibTeX characters in a string.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text safe for BibTeX field values.
    """
    replacements = [
        ("&", r"\&"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("#", r"\#"),
        ("$", r"\$"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


# ------------------------------------------------------------------
# T051a – generate_bibtex
# ------------------------------------------------------------------

def generate_bibtex(papers: list[dict[str, Any]]) -> str:
    """Generate BibTeX file content from a list of paper dicts.

    Each paper dict should contain at minimum ``doi`` and ``title``.
    Optional fields: ``year``, ``abstract``, ``source``, ``authors``.

    Args:
        papers: List of paper metadata dicts (as returned by
                ``Neo4jService.get_project_papers``).

    Returns:
        A string containing the full .bib file content.
    """
    entries: list[str] = []
    seen_keys: set[str] = set()

    for paper in papers:
        doi: str = paper.get("doi", "")
        if not doi:
            continue

        cite_key = _make_cite_key(paper)
        # Ensure unique cite keys
        base_key = cite_key
        counter = 2
        while cite_key in seen_keys:
            cite_key = f"{base_key}{chr(96 + counter)}"  # a, b, c, ...
            counter += 1
        seen_keys.add(cite_key)

        title: str = _escape_bibtex(paper.get("title") or "Unknown Title")
        year: str = str(paper.get("year") or "")
        source: str = _escape_bibtex(paper.get("source") or "")
        abstract: str = _escape_bibtex(
            (paper.get("abstract") or "")[:500]
        )

        # Build author string if available
        authors_raw = paper.get("authors")
        if isinstance(authors_raw, list) and authors_raw:
            author_str = " and ".join(str(a) for a in authors_raw)
        else:
            author_str = "Unknown Author"

        entry_lines = [
            f"@article{{{cite_key},",
            f"  title     = {{{title}}},",
            f"  author    = {{{_escape_bibtex(author_str)}}},",
        ]
        if year:
            entry_lines.append(f"  year      = {{{year}}},")
        if source:
            entry_lines.append(f"  journal   = {{{source}}},")
        entry_lines.append(f"  doi       = {{{doi}}},")
        if abstract:
            entry_lines.append(f"  abstract  = {{{abstract}}},")
        entry_lines.append("}")

        entries.append("\n".join(entry_lines))

    return "\n\n".join(entries) + "\n" if entries else "% No papers to export.\n"


# ------------------------------------------------------------------
# Markdown → LaTeX conversion helpers
# ------------------------------------------------------------------

def _md_to_latex_body(markdown: str) -> str:
    """Convert Markdown body text to basic LaTeX.

    Handles headings (##, ###), bold, italic, inline code, and
    basic list items.  Not a full Markdown parser — handles the
    subset produced by our drafting agent.

    Args:
        markdown: Markdown text content.

    Returns:
        LaTeX body content string.
    """
    lines: list[str] = []

    for line in markdown.split("\n"):
        stripped = line.strip()

        # Headings
        if stripped.startswith("### "):
            heading = stripped[4:]
            lines.append(f"\\subsubsection{{{_escape_bibtex(heading)}}}")
            continue
        if stripped.startswith("## "):
            heading = stripped[3:]
            lines.append(f"\\subsection{{{_escape_bibtex(heading)}}}")
            continue
        if stripped.startswith("# "):
            heading = stripped[2:]
            lines.append(f"\\section{{{_escape_bibtex(heading)}}}")
            continue

        # Bold  **text**  →  \textbf{text}
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", stripped)
        # Italic  *text*  →  \textit{text}
        stripped = re.sub(r"\*(.+?)\*", r"\\textit{\1}", stripped)
        # Inline code  `text`  →  \texttt{text}
        stripped = re.sub(r"`(.+?)`", r"\\texttt{\1}", stripped)

        # Bullet lists
        if stripped.startswith("- "):
            stripped = f"\\item {stripped[2:]}"

        lines.append(stripped)

    return "\n".join(lines)


# ------------------------------------------------------------------
# LaTeX templates
# ------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, str]] = {
    "ieee": {
        "documentclass": "\\documentclass[conference]{IEEEtran}",
        "packages": (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage[utf8]{inputenc}"
        ),
    },
    "acm": {
        "documentclass": "\\documentclass[sigconf]{acmart}",
        "packages": (
            "\\usepackage{amsmath}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage[utf8]{inputenc}"
        ),
    },
    "plain": {
        "documentclass": "\\documentclass[12pt]{article}",
        "packages": (
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{natbib}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage[utf8]{inputenc}"
        ),
    },
}


# ------------------------------------------------------------------
# T051b – format_to_latex
# ------------------------------------------------------------------

def format_to_latex(
    markdown_content: str,
    citations: list[str],
    template: str = "ieee",
) -> str:
    """Convert Markdown content into a complete LaTeX document.

    Wraps the converted body with the appropriate document class,
    packages, and bibliography commands.

    Args:
        markdown_content: Combined Markdown text of all sections.
        citations: List of DOI strings found in the content (for
                   informational comments — actual citations use
                   \\cite{} references in the body).
        template: Template style — 'ieee', 'acm', or 'plain'.

    Returns:
        A complete LaTeX document as a string.
    """
    tmpl = _TEMPLATES.get(template, _TEMPLATES["ieee"])

    body = _md_to_latex_body(markdown_content)

    # Build the LaTeX document
    parts: list[str] = [
        tmpl["documentclass"],
        tmpl["packages"],
        "",
        "\\title{Literature Review}",
        "\\author{ALRS v2 — Automated Literature Review System}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "",
        body,
        "",
        f"% Total DOI citations detected: {len(citations)}",
        "\\bibliographystyle{IEEEtran}" if template == "ieee" else "\\bibliographystyle{plain}",
        "\\bibliography{references}",
        "",
        "\\end{document}",
    ]

    return "\n".join(parts) + "\n"
