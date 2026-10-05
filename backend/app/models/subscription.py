import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Subscription(Base):
    """A user's Stripe billing relationship. At most one row per user.

    Kept separate from `users.plan` on purpose: `plan` is the fast, always-current field every
    other query reads (limits.py, /me), while this table holds the Stripe-specific detail (ids,
    renewal date, cancellation state) the webhook needs to reconcile and the settings page needs
    for "renews on" / "manage billing" copy. A user who has never subscribed has no row here — the
    webhook creates it on the first `checkout.session.completed`.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), index=True)
    # Unique, not primary: re-subscribing after a full cancellation gets a new Stripe subscription
    # id, which overwrites this same row rather than creating a second one for the user.
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), unique=True)
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
