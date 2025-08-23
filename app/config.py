from functools import lru_cache

import humanfriendly
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-level settings."""

    anthropic_api_key: str
    root_path: str = ""
    metrics_enabled: bool = False
    cache_enabled: bool = True
    cache_s3_bucket: str = ""
    cache_s3_prefix: str = "explain-cache/"
    cache_ttl: str = "2d"  # HTTP Cache-Control max-age (e.g., "2d", "48h", "172800s")
    cache_ttl_seconds: int = 172800  # Computed from cache_ttl for Cache-Control header
    log_level: str = "INFO"  # Logging level (DEBUG, INFO, WARNING, ERROR)
    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("cache_ttl_seconds", mode="before")
    @classmethod
    def parse_cache_ttl(cls, v, info):
        """Parse human-readable duration to seconds for HTTP Cache-Control header."""
        if "cache_ttl" in info.data:
            return humanfriendly.parse_timespan(info.data["cache_ttl"])
        return v


@lru_cache
def get_settings():
    """Return the application settings.

    A function so the actual construction is deferred until needed (avoiding test issues), and
    lru_cached for efficiency.
    """
    return Settings()
