"""Validate OpenAlex data once, retaining additional provider metadata."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_doi(value: str) -> str:
    cleaned = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    if re.fullmatch(r"10\.\d{4,9}/\S+", cleaned) is None:
        raise ValueError("A DOI must have the form 10.xxxx/suffix.")
    return cleaned


def normalize_work_id(value: str) -> str:
    cleaned = value.strip()
    for prefix in ("https://openalex.org/", "http://openalex.org/", "openalex:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
    if re.fullmatch(r"[Ww]\d+", cleaned) is None:
        raise ValueError("An OpenAlex work identifier must have the form W123.")
    return cleaned.upper()


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")


class OpenAlexEntity(ProviderMetadata):
    id: str | None = None
    display_name: str | None = None


class OpenAlexAuthorship(ProviderMetadata):
    author: OpenAlexEntity
    institutions: list[OpenAlexEntity] = Field(default_factory=list)


class OpenAlexSource(OpenAlexEntity):
    issn_l: str | None = None
    is_oa: bool | None = None


class OpenAlexLocation(ProviderMetadata):
    source: OpenAlexSource | None = None


class OpenAlexWork(ProviderMetadata):
    id: str | None = None
    doi: str | None = None
    title: str | None = None
    display_name: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    is_retracted: bool | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    authorships: list[OpenAlexAuthorship] = Field(default_factory=list)
    primary_location: OpenAlexLocation | None = None
    topics: list[OpenAlexEntity] = Field(default_factory=list)
    referenced_works: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_work_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return "https://openalex.org/" + normalize_work_id(value)

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_doi(value)

    @field_validator("referenced_works")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        return ["https://openalex.org/" + normalize_work_id(value) for value in values]

    @field_validator("abstract_inverted_index")
    @classmethod
    def validate_abstract_positions(cls, value: dict[str, list[int]] | None) -> dict[str, list[int]] | None:
        if value is not None:
            for positions in value.values():
                if any(position < 0 for position in positions):
                    raise ValueError("Abstract token positions cannot be negative.")
        return value


class OpenAlexPageMetadata(ProviderMetadata):
    count: int | None = Field(default=None, ge=0)
    next_cursor: str | None = None


class OpenAlexWorkPage(ProviderMetadata):
    results: list[OpenAlexWork]
    meta: OpenAlexPageMetadata = Field(default_factory=OpenAlexPageMetadata)
