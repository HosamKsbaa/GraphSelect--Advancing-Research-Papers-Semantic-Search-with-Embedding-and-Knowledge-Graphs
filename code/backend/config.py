"""Application configuration using pydantic-settings.

Loads settings from environment variables and .env file, ignoring extra keys.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for the ALRS GraphSelect system and research agent."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    openalex_email: str | None = None
    default_model: str = "gemini-2.5-flash"
    similarity_threshold: float = 0.3
    max_depth: int = 3
    max_neighbors_per_level: int = 25
    pagerank_iterations: int = 20
    pagerank_damping: float = 0.85
    similarity_weight: float = 0.7
    pagerank_weight: float = 0.3
    density_gated_pagerank: bool = True
    rate_limit_delay_ms: int = 100
    embedding_model: str = "gemini-embedding-2"
    jev_enabled: bool = False
    typesafe_api_key: str = ""
    open_browser: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
