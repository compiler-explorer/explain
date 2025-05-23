from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-level settings."""

    anthropic_api_key: str
    root_path: str = ""
    metrics_enabled: bool = False
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings():
    """Return the application settings.

    A function so the actual construction is deferred until needed (avoiding test issues), and
    lru_cached for efficiency.
    """
    return Settings()
