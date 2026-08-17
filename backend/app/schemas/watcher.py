"""Request and response shapes for the watcher API.

The normalisation here is load-bearing, not cosmetic — see `normalise_subreddit`.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import DIRECTION_REQUESTING, STATUS_ACTIVE

# Reddit's own rule: 3-21 characters, letters, digits and underscores.
SUBREDDIT_PATTERN = re.compile(r"^[a-z0-9_]{3,21}$")

# An intent this short cannot produce a meaningful embedding — "dev" is a word, not a description
# of what someone wants to find. Rejecting it here beats silently matching everything.
MIN_INTENT_CHARS = 15
MAX_INTENT_CHARS = 2000

# Bounds the per-watcher work regardless of plan; the real cap is the tier's subreddit pool.
MAX_SUBREDDITS_PER_WATCHER = 50


# Strip the r/ prefix and lowercase a subreddit name.
#
# Casing is not cosmetic: the ingestion worker builds its poll list from these strings and the
# matcher does an exact-string `subreddits.any(post.subreddit)`. "ForHire" and "forhire" would be
# polled twice *and* would fail to link posts back to one of the two watchers.
def normalise_subreddit(value: str) -> str:
    cleaned = value.strip().lstrip("/")
    if cleaned.lower().startswith("r/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip("/").lower()

    if not SUBREDDIT_PATTERN.match(cleaned):
        raise ValueError(
            f"{value!r} is not a valid subreddit name "
            "(3-21 characters, letters, digits and underscores only)"
        )
    return cleaned


# Normalise a whole list and drop duplicates, preserving the order the user typed.
def normalise_subreddits(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        name = normalise_subreddit(value)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


class WatcherCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    intent_text: Annotated[str, Field(min_length=MIN_INTENT_CHARS, max_length=MAX_INTENT_CHARS)]
    subreddits: Annotated[
        list[str], Field(min_length=1, max_length=MAX_SUBREDDITS_PER_WATCHER)
    ]
    direction: Literal["requesting", "offering"] = DIRECTION_REQUESTING
    status: Literal["active", "paused"] = STATUS_ACTIVE

    @field_validator("subreddits")
    @classmethod
    def _normalise(cls, value: list[str]) -> list[str]:
        return normalise_subreddits(value)

    @field_validator("name", "intent_text")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class WatcherUpdate(BaseModel):
    """Every field optional — this is a PATCH. `None` means "leave alone", not "clear"."""

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    intent_text: (
        Annotated[str, Field(min_length=MIN_INTENT_CHARS, max_length=MAX_INTENT_CHARS)] | None
    ) = None
    subreddits: (
        Annotated[list[str], Field(min_length=1, max_length=MAX_SUBREDDITS_PER_WATCHER)] | None
    ) = None
    direction: Literal["requesting", "offering"] | None = None
    status: Literal["active", "paused"] | None = None

    @field_validator("subreddits")
    @classmethod
    def _normalise(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalise_subreddits(value)

    @field_validator("name", "intent_text")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class WatcherRead(BaseModel):
    """What the API returns. Deliberately omits `intent_embedding` — 1536 floats nobody needs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    intent_text: str
    subreddits: list[str]
    direction: str
    status: str
    created_at: datetime
    # Null until the embedding worker has processed it; the UI can show "preparing…" on that.
    embedded_at: datetime | None
