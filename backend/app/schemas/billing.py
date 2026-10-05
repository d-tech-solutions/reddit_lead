"""Request and response shapes for the billing API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlanRead(BaseModel):
    """One row of the pricing table — the same numbers `core.constants.TIER_LIMITS` enforces
    server-side, so the pricing UI can never drift from what the API actually allows."""

    id: str
    price_cents: int
    max_watchers: int | None
    max_subreddits: int | None


class SubscriptionRead(BaseModel):
    plan: str
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool


class CheckoutRequest(BaseModel):
    # Mirrors `app.core.constants.PAID_PLANS` — a literal so an unknown plan name is a 422 from
    # FastAPI's own validation rather than reaching the Stripe price lookup.
    plan: Literal["standard", "premium", "enterprise"]


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str
