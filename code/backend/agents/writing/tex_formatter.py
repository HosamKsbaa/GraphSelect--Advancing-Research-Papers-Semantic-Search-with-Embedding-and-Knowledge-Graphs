"""TeX formatting utilities for the writing pipeline.

Pure-Python, deterministic functions that convert Markdown drafts
to LaTeX and generate BibTeX entries from paper metadata.  These
are used by the export tools, not as ADK tools directly.

Functions:
    - format_to_latex: Markdown → LaTeX with template wrapping
    - generate_bibtex: Paper dicts → .bib file content
    - _make_cite_key: Deterministic cite-key generator
    - _escape_bibtex: Strict escaping of LaTeX special characters
    - _md_to_latex_body: Markdown to LaTeX body converter
"""
from __future__ import annotations

import re
from typing import Any


# ------------------------------------------------------------------
# BibTeX key generation
# ------------------------------------------------------------------

def _make_cite_key(paper: dict[str, Any]) -> str:
    """Generate a deterministic BibTeX cite key from a paper dict.

    Uses the first word of the title (or first author surname if title is missing),
    followed by the 4-digit publication year.

    Args:
        paper: Dict with at least 'doi' and optionally 'title', 'year', 'authors'.

    Returns:
        A lowercase alphanumeric string suitable for use as a BibTeX cite key
        (e.g., 'attention2017', 'vaswani2017').
    """
    title: str = str(paper.get("title") or "").strip()
    year: int | None = paper.get("year")
    doi: str = str(paper.get("doi", "unknown")).strip()
    authors = paper.get("authors") or paper.get("author")

    if title:
        words = title.split()
        first_word = re.sub(r"[^a-zA-Z0-9]", "", words[0]) if words else "paper"
    elif authors:
        if isinstance(authors, list) and authors:
            first_author = str(authors[0])
        else:
            first_author = str(authors)
        # Extract surname (last token or first word)
        surname = first_author.split()[-1] if first_author.split() else "author"
        first_word = re.sub(r"[^a-zA-Z0-9]", "", surname)
    else:
        # Use DOI suffix as fallback
        first_word = re.sub(r"[^a-zA-Z0-9]", "", doi.split("/")[-1])[:12]

    if not first_word:
        first_word = "paper"

    year_str = str(year) if year else "XXXX"
    return f"{first_word.lower()}{year_str}"


def _escape_bibtex(text: str) -> str:
    """Strictly escape special LaTeX/BibTeX characters in a string.

    Escapes: &, %, _, #, $ while preventing double-escaping.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text safe for BibTeX field values and LaTeX bodies.
    """
    if not text:
        return ""

    replacements = [
        (r"(?<!\\)&", r"\&"),
        (r"(?<!\\)%", r"\%"),
        (r"(?<!\\)_", r"\_"),
        (r"(?<!\\)#", r"\#"),
        (r"(?<!\\)\$", r"\$"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text


# ------------------------------------------------------------------
# T051a – generate_bibtex
# ------------------------------------------------------------------

def generate_bibtex(papers: list[dict[str, Any]]) -> str:
    """Generate BibTeX file content from a list of paper dicts.

    Each paper dict should contain at minimum ``doi`` and ``title``.
    Optional fields: ``year``, ``abstract``, ``source``, ``authors`` / ``author``.

    Ensures collision-free unique cite keys using sequential suffixes
    (e.g., 'graph2021', 'graph2021b', 'graph2021c').

    Args:
        papers: List of paper metadata dicts (as returned by
                ``Neo4jService.get_project_papers``).

    Returns:
        A string containing the full .bib file content.
    """
    entries: list[str] = []
    seen_keys: set[str] = set()

    for paper in papers:
        doi: str = str(paper.get("doi", "")).strip()
        if not doi:
            continue

        cite_key = _make_cite_key(paper)
        # Collision-free deterministic deduplication: key, keyb, keyc, ...
        base_key = cite_key
        counter = 2
        while cite_key in seen_keys:
            cite_key = f"{base_key}{chr(96 + counter)}"  # 'b', 'c', 'd', ...
            counter += 1
        seen_keys.add(cite_key)

        title: str = _escape_bibtex(str(paper.get("title") or "Unknown Title"))
        year: str = str(paper.get("year") or "")
        source: str = _escape_bibtex(str(paper.get("source") or paper.get("journal") or ""))
        abstract: str = _escape_bibtex(
            str(paper.get("abstract") or "")[:500]
        )

        # Build author string if available
        authors_raw = paper.get("authors") or paper.get("author")
        if isinstance(authors_raw, list) and authors_raw:
            author_str = " and ".join(str(a) for a in authors_raw)
        elif isinstance(authors_raw, str) and authors_raw.strip():
            author_str = authors_raw.strip()
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

    Handles headings (####, ###, ##, #), bold (**), italic (*),
    inline code (`), code blocks, blockquotes, and lists.

    Args:
        markdown: Markdown text content.

    Returns:
        LaTeX body content string.
    """
    if not markdown:
        return ""

    lines: list[str] = []
    in_code_block = False
    in_itemize = False
    in_enumerate = False

    for line in markdown.split("\n"):
        stripped = line.strip()

        # Handle code blocks
        if stripped.startswith("```"):
            if in_code_block:
                lines.append(r"\end{verbatim}")
                in_code_block = False
            else:
                lines.append(r"\begin{verbatim}")
                in_code_block = True
            continue

        if in_code_block:
            lines.append(line)
            continue

        # Handle list boundaries
        is_bullet = stripped.startswith("- ") or stripped.startswith("* ")
        is_enum = bool(re.match(r"^\d+\.\s+", stripped))

        if is_bullet:
            if not in_itemize:
                if in_enumerate:
                    lines.append(r"\end{enumerate}")
                    in_enumerate = False
                lines.append(r"\begin{itemize}")
                in_itemize = True
            content = stripped[2:].strip()
            # Format text inside list item
            content = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", content)
            content = re.sub(r"\*(.+?)\*", r"\\textit{\1}", content)
            content = re.sub(r"`(.+?)`", r"\\texttt{\1}", content)
            lines.append(f"\\item {content}")
            continue
        elif in_itemize:
            lines.append(r"\end{itemize}")
            in_itemize = False

        if is_enum:
            if not in_enumerate:
                if in_itemize:
                    lines.append(r"\end{itemize}")
                    in_itemize = False
                lines.append(r"\begin{enumerate}")
                in_enumerate = True
            content = re.sub(r"^\d+\.\s+", "", stripped).strip()
            content = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", content)
            content = re.sub(r"\*(.+?)\*", r"\\textit{\1}", content)
            content = re.sub(r"`(.+?)`", r"\\texttt{\1}", content)
            lines.append(f"\\item {content}")
            continue
        elif in_enumerate:
            lines.append(r"\end{enumerate}")
            in_enumerate = False

        # Blockquotes
        if stripped.startswith("> "):
            quote_text = stripped[2:].strip()
            quote_text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", quote_text)
            quote_text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", quote_text)
            lines.append(f"\\begin{{quote}}\n{quote_text}\n\\end{{quote}}")
            continue

        # Headings
        if stripped.startswith("#### "):
            heading = stripped[5:]
            lines.append(f"\\paragraph{{{_escape_bibtex(heading)}}}")
            continue
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

        # Text formatting
        # Bold  **text**  →  \textbf{text}
        formatted = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", stripped)
        # Italic  *text*  →  \textit{text}
        formatted = re.sub(r"\*(.+?)\*", r"\\textit{\1}", formatted)
        # Inline code  `text`  →  \texttt{text}
        formatted = re.sub(r"`(.+?)`", r"\\texttt{\1}", formatted)

        lines.append(formatted)

    # Close any open list environments
    if in_itemize:
        lines.append(r"\end{itemize}")
    if in_enumerate:
        lines.append(r"\end{enumerate}")
    if in_code_block:
        lines.append(r"\end{verbatim}")

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
    """Convert Markdown content into a complete, compilable LaTeX document.

    Wraps the converted body with the appropriate document class,
    packages, metadata headers, and bibliography commands.

    Args:
        markdown_content: Combined Markdown text of all sections.
        citations: List of DOI strings found in the content (for
                   informational comments — actual citations use
                   \\cite{} references in the body).
        template: Template style — 'ieee', 'acm', or 'plain'. Defaults to 'ieee'.

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
