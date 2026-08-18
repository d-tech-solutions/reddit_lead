from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

# No Arq pool here: the API no longer enqueues anything directly. A new watcher becomes visible to
# the matcher on the next ingestion cycle purely by existing (no embedding to trigger), and editing
# `intent_text` takes effect on the very next post the matcher considers.
app = FastAPI(title="PostPing API")

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
