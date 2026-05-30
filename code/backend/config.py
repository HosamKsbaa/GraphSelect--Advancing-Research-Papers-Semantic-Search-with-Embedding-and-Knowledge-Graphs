"""ALRS v2 backend configuration via Pydantic settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Google Gemini API ---
    gemini_api_key: str = Field(..., description="Gemini API key for embeddings")

    # --- OpenAlex API ---
    openalex_api_key: str = Field(..., description="OpenAlex API key (required)")

    # --- Neo4j ---
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(..., description="Neo4j password")

    # --- MySQL ---
    mysql_host: str = Field(default="localhost")
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_user: str = Field(default="alrs")
    mysql_password: str = Field(..., description="MySQL password")
    mysql_database: str = Field(default="alrs")

    # --- Application ---
    log_retention_hours: int = Field(default=24, ge=1, le=720)
    embedding_dimensions: int = Field(default=768)
    openalex_rate_limit: float = Field(default=9.0, ge=0.1, le=100.0)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, v: int) -> int:
        """Ensure embedding dimensions are in the supported range."""
        allowed = {128, 256, 384, 512, 768, 1024, 1536, 3072}
        if v not in allowed:
            raise ValueError(
                f"embedding_dimensions must be one of {sorted(allowed)}, got {v}"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()  # type: ignore[call-arg]
