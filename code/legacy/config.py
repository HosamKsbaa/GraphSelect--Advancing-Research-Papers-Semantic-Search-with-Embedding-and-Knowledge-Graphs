"""Application configuration using pydantic-settings.

Loads settings from environment variables and .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for the GraphSelect algorithm.

    All fields can be overridden via environment variables or a .env file.
    """

    model_config = SettingsConfigDict(env_file=".env")

    gemini_api_key: str = ""
    openalex_email: str | None = None
    similarity_threshold: float = 0.3
    max_depth: int = 3
    max_neighbors_per_level: int = 25
    pagerank_iterations: int = 20
    pagerank_damping: float = 0.85
    similarity_weight: float = 0.7
    pagerank_weight: float = 0.3
    rate_limit_delay_ms: int = 100
    embedding_model: str = "gemini-embedding-001"
    open_browser: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
