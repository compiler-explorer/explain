from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-level settings."""

    anthropic_api_key: str
    root_path: str = ""
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
