"""Identifier extractor and fuzzy title matching for continuous ingestion.

Complies with Constitution v2.2.1:
- C7: Strict static typing.
- C9: Granular functions under 25 lines (SRP / SLAP).
- C11: Intention-revealing domain types.
"""
from __future__ import annotations

import difflib
import re
import uuid
from typing import Any

from features.ingestion.models import IdentifierType, TitleConfirmationChip

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
ARXIV_PATTERN = re.compile(r"(?:arxiv:\s*)?(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
DOI_URL_PATTERN = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)


def clean_punctuation(raw_text: str) -> str:
    """Strip surrounding brackets, parentheses, and trailing punctuation."""
    text = raw_text.strip()
    while text.startswith(("(", "[", "{", "<", '"', "'")):
        text = text[1:].strip()
    while text.endswith((".", ",", ";", ":", "!", "?", ")", "]", "}", ">", '"', "'")):
        text = text[:-1].strip()
    return text


def extract_dois(text: str) -> list[str]:
    """Extract canonical lowercase DOIs with surrounding punctuation removed."""
    matches = DOI_PATTERN.findall(text)
    dois: list[str] = []
    for match in matches:
        cleaned = clean_punctuation(match).lower()
        if cleaned.startswith("10.") and "/" in cleaned and cleaned not in dois:
            dois.append(cleaned)
    return dois


def extract_arxiv_ids(text: str) -> list[str]:
    """Extract normalized arXiv identifiers from conversational text."""
    matches = ARXIV_PATTERN.findall(text)
    arxiv_ids: list[str] = []
    for match in matches:
        cleaned = clean_punctuation(match).lower()
        if re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", cleaned) and cleaned not in arxiv_ids:
            arxiv_ids.append(cleaned)
    return arxiv_ids


def extract_urls(text: str) -> list[str]:
    """Extract valid HTTP/HTTPS URLs from conversational text."""
    matches = URL_PATTERN.findall(text)
    urls: list[str] = []
    for match in matches:
        cleaned = clean_punctuation(match)
        if cleaned.startswith("http") and cleaned not in urls:
            urls.append(cleaned)
    return urls


def normalize_identifier_input(raw_input: str) -> tuple[IdentifierType, str]:
    """Normalize raw string to canonical form and identify its type."""
    cleaned = clean_punctuation(raw_input)
    doi_url_match = DOI_URL_PATTERN.match(cleaned)
    if doi_url_match:
        return IdentifierType.DOI, clean_punctuation(doi_url_match.group(1)).lower()
    arxiv_url_match = ARXIV_URL_PATTERN.match(cleaned)
    if arxiv_url_match:
        return IdentifierType.ARXIV, clean_punctuation(arxiv_url_match.group(1)).lower()
    dois = extract_dois(cleaned)
    if dois:
        return IdentifierType.DOI, dois[0]
    arxiv_ids = extract_arxiv_ids(cleaned)
    if arxiv_ids:
        return IdentifierType.ARXIV, arxiv_ids[0]
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return IdentifierType.URL, cleaned
    return IdentifierType.TITLE, cleaned


def extract_all_identifiers(text: str) -> list[tuple[IdentifierType, str]]:
    """Scan text and return all distinct academic identifiers found."""
    results: list[tuple[IdentifierType, str]] = []
    for doi in extract_dois(text):
        results.append((IdentifierType.DOI, doi))
    for arxiv_id in extract_arxiv_ids(text):
        if not any(r[1] == arxiv_id for r in results):
            results.append((IdentifierType.ARXIV, arxiv_id))
    for url in extract_urls(text):
        doi_match = DOI_URL_PATTERN.match(url)
        if not doi_match and not any(r[1] == url for r in results):
            results.append((IdentifierType.URL, url))
    return results


def _tokenize_title(title: str) -> str:
    """Normalize and sort words in a title string for token similarity."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    words = sorted([w for w in cleaned.split() if len(w) > 1])
    return " ".join(words)


def compute_title_similarity(candidate: str, target: str) -> float:
    """Compute maximum of raw sequence and token sort similarity ratios."""
    if not candidate or not target:
        return 0.0
    clean_cand = re.sub(r"\s+", " ", candidate.lower().strip())
    clean_target = re.sub(r"\s+", " ", target.lower().strip())
    raw_ratio = difflib.SequenceMatcher(None, clean_cand, clean_target).ratio()
    tok_cand = _tokenize_title(candidate)
    tok_target = _tokenize_title(target)
    token_ratio = difflib.SequenceMatcher(None, tok_cand, tok_target).ratio()
    return max(raw_ratio, token_ratio)


async def match_title_candidate(
    title_text: str,
    openalex_service: Any,
    threshold: float = 0.90,
) -> TitleConfirmationChip | None:
    """Search OpenAlex by title; return confirmation chip if similarity >= threshold."""
    candidates = await _fetch_openalex_candidates(title_text, openalex_service)
    if not candidates:
        return None
    best_candidate, best_score = _find_best_candidate(title_text, candidates)
    if best_score < threshold or best_candidate is None:
        return None
    return _build_confirmation_chip(title_text, best_candidate, best_score)


async def _fetch_openalex_candidates(title_text: str, openalex_service: Any) -> list[Any]:
    """Retrieve search candidates from OpenAlex API safely."""
    if not hasattr(openalex_service, "search_by_title"):
        return []
    try:
        res = await openalex_service.search_by_title(title_text, max_results=5)
        return [c for c in res] if isinstance(res, list) else []
    except Exception:
        return []


def _find_best_candidate(title_text: str, candidates: list[Any]) -> tuple[Any | None, float]:
    """Identify highest similarity candidate paper from candidate list."""
    best_candidate: Any | None = None
    best_score = 0.0
    for cand in candidates:
        cand_title = getattr(cand, "title", "")
        score = compute_title_similarity(title_text, cand_title)
        if score > best_score:
            best_score = score
            best_candidate = cand
    return best_candidate, best_score


def _build_confirmation_chip(
    title_text: str, candidate: Any, similarity_score: float
) -> TitleConfirmationChip:
    """Instantiate a TitleConfirmationChip model from matched candidate."""
    raw_oa_id = getattr(candidate, "openalex_id", None) or getattr(candidate, "id", "")
    oa_id = str(raw_oa_id).replace("https://openalex.org/", "").strip() if raw_oa_id else f"W{uuid.uuid4().hex[:8]}"
    raw_doi = getattr(candidate, "doi", None)
    clean_doi = str(raw_doi).replace("https://doi.org/", "").strip() if raw_doi else None
    return TitleConfirmationChip(
        chip_id=str(uuid.uuid4()),
        extracted_title=title_text.strip(),
        resolved_openalex_id=oa_id,
        resolved_doi=clean_doi,
        resolved_title=getattr(candidate, "title", title_text.strip()),
        similarity_score=round(similarity_score, 4),
        status="pending",
    )
