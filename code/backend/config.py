"""ALRS v2 backend configuration via Pydantic settings."""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_openalex_api_key_here"}
_PLACEHOLDER_PROJECTS = {"", "your-gcp-project-id", "your_project_id_here"}


def find_env_file() -> Path:
    """Find the canonical .env file location across execution contexts."""
    # 1. Check explicit environment variable override
    env_override = os.environ.get("ENV_FILE") or os.environ.get("ALRS_ENV_FILE")
    if env_override:
        p = Path(env_override).resolve()
        if p.exists() or p.parent.exists():
            return p

    # 2. Check router.ENV_FILE if patched in tests or modified
    try:
        if "features.settings.router" in sys.modules:
            router_mod = sys.modules["features.settings.router"]
            router_env = getattr(router_mod, "ENV_FILE", None)
            if router_env is not None:
                p = Path(router_env).resolve()
                if p.exists() or p.parent.exists():
                    return p
    except Exception:
        pass

    # 3. Check backend directory (.env next to config.py)
    backend_dir = Path(__file__).resolve().parent
    backend_env = backend_dir / ".env"
    if backend_env.exists():
        return backend_env

    # 4. Check workspace / repo root directory (.env in parent directory)
    root_env = backend_dir.parent / ".env"
    if root_env.exists():
        return root_env

    # 5. Check current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    return backend_env


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, _env_file: Path | str | None = None, **values: Any) -> None:
        if _env_file is None:
            _env_file = find_env_file()
        super().__init__(_env_file=_env_file, **values)

    # --- Google Gemini / Vertex AI ---
    use_vertex_ai: bool = Field(default=False, description="Whether to use Vertex AI instead of Google AI Studio")
    vertex_project: str | None = Field(default=None, description="Google Cloud Project ID for Vertex AI")
    vertex_location: str = Field(default="us-central1", description="Vertex AI location region")
    gemini_api_key: str | None = Field(default=None, description="Gemini API key for Google AI Studio (optional if Vertex AI is active)")

    @model_validator(mode="after")
    def resolve_auth_mode(self) -> "Settings":
        """If USE_VERTEX_AI is not explicitly set in input, infer from configured credentials."""
        has_vertex = bool(self.vertex_project and self.vertex_project.strip() not in _PLACEHOLDER_PROJECTS)
        has_studio = bool(self.gemini_api_key and self.gemini_api_key.strip() not in _PLACEHOLDER_KEYS)
        if "use_vertex_ai" not in self.model_fields_set or (not self.use_vertex_ai and has_vertex and not has_studio):
            if has_vertex and not has_studio:
                self.use_vertex_ai = True
            else:
                self.use_vertex_ai = False
        return self


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
    host_projects_dir: str | None = Field(default=None, description="Directory for per-project artifacts on the host OS")

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
    target_env = find_env_file()
    settings = Settings(_env_file=target_env)  # type: ignore[call-arg]

    # Propagate to standard OS environment variables so google-genai and google-adk
    # automatically pick up the correct platform and credentials.
    if settings.use_vertex_ai:
        os.environ["USE_VERTEX_AI"] = "true"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if settings.vertex_project and settings.vertex_project.strip() not in _PLACEHOLDER_PROJECTS:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.vertex_project.strip()
            os.environ["VERTEX_PROJECT"] = settings.vertex_project.strip()
        else:
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("VERTEX_PROJECT", None)
        if settings.vertex_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = settings.vertex_location.strip()
            os.environ["VERTEX_LOCATION"] = settings.vertex_location.strip()
        # Clear API key to prevent SDK confusion
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
    else:
        os.environ["USE_VERTEX_AI"] = "false"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        if settings.gemini_api_key and settings.gemini_api_key.strip() not in _PLACEHOLDER_KEYS:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key.strip()
            os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key.strip()
        else:
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("VERTEX_PROJECT", None)

    return settings


