from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./job_hunter.db"
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    # "auto" tries Claude first and falls back to Gemini; "anthropic" / "gemini" use one provider only.
    llm_provider: str = "auto"
    anthropic_profile_model: str = "claude-sonnet-5-5"
    anthropic_scoring_model: str = "claude-haiku-5-5"
    gemini_model: str = "gemini-3.8-flash"
    llm_timeout_seconds: float = 90.0
    brave_search_api_key: str | None = None
    notion_token: str | None = None
    notion_database_id: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
