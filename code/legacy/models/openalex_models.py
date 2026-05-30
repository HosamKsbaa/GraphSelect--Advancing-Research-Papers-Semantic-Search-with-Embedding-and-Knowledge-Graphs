"""Pydantic models for OpenAlex API responses.

These models mirror the JSON structure returned by the OpenAlex Works API
and provide validated, typed access to paper metadata.
"""

from typing import Any

from pydantic import BaseModel


class Author(BaseModel):
    """An author entity from OpenAlex."""

    id: str | None = None
    display_name: str | None = None
    orcid: str | None = None


class Authorship(BaseModel):
    """Author–work relationship with institutional affiliations."""

    author: Author
    institutions: list[dict[str, Any]] = []
    author_position: str | None = None


class OpenAccess(BaseModel):
    """Open-access availability information for a work."""

    is_oa: bool = False
    oa_status: str | None = None
    oa_url: str | None = None


class PrimaryLocation(BaseModel):
    """Primary publication location of a work."""

    source: dict[str, Any] | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    is_oa: bool = False


class Work(BaseModel):
    """A scholarly work (paper) as returned by the OpenAlex API."""

    id: str | None = None
    doi: str | None = None
    title: str | None = None
    display_name: str | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    authorships: list[Authorship] = []
    cited_by_count: int = 0
    publication_date: str | None = None
    publication_year: int | None = None
    type: str | None = None
    referenced_works: list[str] = []
    primary_location: PrimaryLocation | None = None
    open_access: OpenAccess | None = None
    ids: dict[str, str] | None = None


class WorksMeta(BaseModel):
    """Pagination and timing metadata from an OpenAlex response."""

    count: int = 0
    db_response_time_ms: int = 0
    page: int = 1
    per_page: int = 25


class WorksResponse(BaseModel):
    """Top-level response from the OpenAlex /works endpoint."""

    meta: WorksMeta | None = None
    results: list[Work] = []
