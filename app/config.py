from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-level settings."""

    anthropic_api_key: str
    root_path: str = ""
    metrics_enabled: bool = False
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
