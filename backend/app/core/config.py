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

    # Matcher + LLM verifier. Every active watcher subscribed to a post's subreddit is judged in
    # one batched call per post — no embedding stage, no vector gate.
    OPENAI_API_KEY: str = ""
    VERIFIER_MODEL: str = "gpt-4o-mini"
    # Watchers per LLM call. Bounds prompt size and, if one call fails, how many watchers are
    # affected — a post with more candidates than this is split into several calls.
    MATCH_BATCH_SIZE: int = 15
    MATCH_BACKFILL_INTERVAL_MINUTES: int = 5
    MATCH_BACKFILL_LIMIT: int = 200

    # Auth (Clerk)
    CLERK_SECRET_KEY: str = ""
    # Comma-separated frontend origins allowed to mint tokens for this API. Leaving this empty
    # skips the `azp` check, which would let a token issued for a different app authenticate here —
    # acceptable locally, not in production.
    CLERK_AUTHORIZED_PARTIES: str = ""

    # Billing (Stripe). Checkout/portal redirect back to FRONTEND_URL; the webhook is verified
    # against STRIPE_WEBHOOK_SECRET rather than authenticated like the rest of the API.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STANDARD: str = ""
    STRIPE_PRICE_PREMIUM: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""
    FRONTEND_URL: str = "http://localhost:3000"

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
