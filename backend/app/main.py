import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# Hold one Arq pool for the process so watcher writes can hand work to the embedding worker.
#
# A failed connection is logged rather than fatal: the API's job is serving requests, and the
# embedding worker's backfill sweep already recovers any watcher left without a vector. Refusing
# to boot because a background queue is down would be the worse trade.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = None
    try:
        app.state.redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    except Exception:
        logger.exception("api: could not connect to Redis, embed jobs will not be enqueued")

    try:
        yield
    finally:
        if app.state.redis is not None:
            await app.state.redis.aclose()


app = FastAPI(title="PostPing API", lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
