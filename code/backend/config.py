"""ALRS v2 backend configuration via Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Google Gemini / Vertex AI ---
    use_vertex_ai: bool = Field(default=True, description="Whether to use Vertex AI instead of Google AI Studio")
    vertex_project: str | None = Field(default=None, description="Google Cloud Project ID for Vertex AI")
    vertex_location: str = Field(default="us-central1", description="Vertex AI location region")
    gemini_api_key: str | None = Field(default=None, description="Gemini API key for Google AI Studio (optional if Vertex AI is active)")


    # --- OpenAlex API ---
    openalex_api_key: str = Field(..., description="OpenAlex API key (required)")
    openalex_email: str | None = Field(default=None, description="Email for OpenAlex polite pool")

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
    embedding_model: str = Field(default="gemini-embedding-2")
    embedding_dimensions: int = Field(default=768)
    openalex_rate_limit: float = Field(default=9.0, ge=0.1, le=100.0)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000, ge=1, le=65535)

    # --- ADK / Agent Configuration ---
    adk_model_name: str = Field(default="gemini-3.5-flash", description="Model for reasoning agents")
    token_budget_default: int = Field(default=500000, ge=1000, description="Default token budget per pipeline run")
    token_budget_warn_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Warn at this fraction of budget")
    max_research_questions: int = Field(default=6, ge=1, le=20, description="Max questions per project")
    similarity_threshold_default: float = Field(default=0.6, ge=0.0, le=1.0, description="Default relevance threshold")
    projects_dir: str = Field(default_factory=lambda: str(Path.home() / ".alrs" / "projects"), description="Directory for per-project artifacts")

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
    settings = Settings()  # type: ignore[call-arg]

    # Propagate to standard OS environment variables so google-genai and google-adk
    # automatically pick up the correct platform and credentials.
    import os
    if settings.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if settings.vertex_project:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.vertex_project
        if settings.vertex_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = settings.vertex_location
        # Clear API key to prevent SDK confusion
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
    else:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        if settings.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
            os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key

    return settings

