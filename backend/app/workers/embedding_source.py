"""Turn text into embedding vectors via OpenAI.

Structured as a protocol plus one implementation so the worker code depends on the interface
rather than the SDK — the test suite substitutes a fake that satisfies the same protocol.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.core.constants import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

# `text-embedding-3-small` accepts 8191 tokens per input. Rather than pull in a tokenizer just for
# this, budget ~4 characters per token and truncate — the cap only needs to be safe, not exact.
MAX_INPUT_CHARS = 8000 * 4

# USD per million tokens for `text-embedding-3-small`, used only for the spend line in the logs.
COST_PER_MILLION_TOKENS = 0.02


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def close(self) -> None: ...


# Build the single string that represents a post for matching purposes.
# Title carries most of the intent signal, so it leads; body is appended when present.
def post_to_text(title: str, body: str) -> str:
    combined = f"{title}\n\n{body}".strip() if body.strip() else title.strip()
    return combined[:MAX_INPUT_CHARS]


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    # Embed a batch of texts in one API call and return vectors in the same order as the input.
    # Batching matters here because cost and latency both scale with the number of requests.
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = await self._client.embeddings.create(model=self._model, input=texts)
        # The API documents order preservation, but the matcher silently mis-pairs vectors with
        # posts if that ever breaks, so sort by index rather than trusting arrival order.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]

        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"model {self._model!r} returned {len(vector)} dimensions, "
                    f"but the database column is fixed at {EMBEDDING_DIMENSIONS}"
                )

        _log_usage(self._model, len(texts), getattr(response, "usage", None))
        return vectors

    async def close(self) -> None:
        await self._client.close()


# Log tokens and estimated dollar cost per call, so embedding spend is visible from day one
# (ARCHITECTURE.md §7 asks for per-call cost tracking).
def _log_usage(model: str, batch_size: int, usage: Any) -> None:
    tokens = getattr(usage, "total_tokens", None) if usage else None
    if tokens is None:
        logger.info("embed: model=%s batch=%d tokens=unknown", model, batch_size)
        return

    cost = tokens / 1_000_000 * COST_PER_MILLION_TOKENS
    logger.info(
        "embed: model=%s batch=%d tokens=%d est_cost_usd=%.6f", model, batch_size, tokens, cost
    )


# Construct the provider the worker should use, failing immediately with an actionable message
# when the API key is missing rather than at the first embed call.
def build_embedding_provider(api_key: str, model: str) -> EmbeddingProvider:
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required to run the embedding worker. "
            "Set it in backend/.env for local runs, or in the root .env for docker compose."
        )
    return OpenAIEmbeddingProvider(api_key, model)
