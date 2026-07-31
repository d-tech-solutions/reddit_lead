from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "local"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postping"
    REDIS_URL: str = "redis://localhost:6379/0"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: str = ""

    # Ingestion worker
    REDDIT_FETCH_MODE: str = "rss"  # "rss" (no signup, dev/test) or "api" (official, needs approval)
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "postping/0.1"
    REDDIT_POLL_INTERVAL_SECONDS: int = 60

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
