import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """A PostPing account, keyed to a Clerk identity.

    Clerk owns authentication; this table owns everything the app needs to attach to a person —
    their plan, and eventually their billing and notification channels. Rows are created
    just-in-time on the first authenticated request rather than by a Clerk webhook; see
    docs/auth-and-watchers/ for what that defers.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The `sub` claim from Clerk's session token. Unique because it is the identity we join on.
    clerk_user_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    # Nullable: the session token does not always carry an email claim, and the account is usable
    # without one until the notification worker needs somewhere to send.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Overrides `email` as the notification delivery address when set. Kept separate rather than
    # reusing `email` because `get_or_create_user` re-syncs `email` from Clerk's claims on every
    # login, which would silently clobber an override living in that column.
    notification_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="free", index=True)
    # Staff flag, set manually (no Clerk webhook to sync a role claim from). Grants access to the
    # /admin API and UI, in addition to everything a normal account can do.
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Blocks API access when False, without deleting anything — see `get_current_user`. Distinct
    # from a Clerk-side ban since it's ours to flip without touching the Clerk identity.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
