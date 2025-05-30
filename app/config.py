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
    cache_ttl: str = "2d"  # Human-readable duration (e.g., "2d", "48h", "172800s")
    cache_ttl_seconds: int = 172800  # Will be computed from cache_ttl
    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("cache_ttl_seconds", mode="before")
    @classmethod
    def parse_cache_ttl(cls, v, info):
        """Parse human-readable cache TTL to seconds."""
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
