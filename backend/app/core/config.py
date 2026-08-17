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

    # Embedding worker
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 100
    # How often the backfill sweep runs, in minutes. Must divide 60 evenly (it becomes an Arq cron
    # minute set); values that don't are rounded down to the nearest divisor.
    EMBED_BACKFILL_INTERVAL_MINUTES: int = 5
    EMBED_BACKFILL_LIMIT: int = 500

    # Matcher + LLM verifier
    ANTHROPIC_API_KEY: str = ""
    VERIFIER_MODEL: str = "claude-haiku-4-5"
    # Candidate watchers per post handed to the verifier. Deliberately generous: on the only real
    # data measured so far, K=5 would have contained zero true matches. Calibrate from the logged
    # similarity/verdict pairs in `matches`, not by guessing — see docs/PROGRESS.md 2026-07-30.
    MATCH_TOP_K: int = 10
    # How hard to penalise a post pointing the wrong way on the request/offer axis.
    MATCH_DIRECTION_WEIGHT: float = 1.0
    MATCH_BACKFILL_INTERVAL_MINUTES: int = 5
    MATCH_BACKFILL_LIMIT: int = 200

    # Auth (Clerk)
    CLERK_SECRET_KEY: str = ""
    # Comma-separated frontend origins allowed to mint tokens for this API. Leaving this empty
    # skips the `azp` check, which would let a token issued for a different app authenticate here —
    # acceptable locally, not in production.
    CLERK_AUTHORIZED_PARTIES: str = ""

    @property
    def clerk_authorized_parties(self) -> list[str]:
        return [
            party.strip() for party in self.CLERK_AUTHORIZED_PARTIES.split(",") if party.strip()
        ]

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
