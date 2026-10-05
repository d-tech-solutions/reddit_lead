"""Request and response shapes for the superadmin API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.watcher import WatcherRead


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    plan: str
    is_active: bool
    is_superadmin: bool
    created_at: datetime
    watcher_count: int


class AdminUserDetail(AdminUserRead):
    watchers: list[WatcherRead]


class AdminUserUpdate(BaseModel):
    """Every field optional — this is a PATCH. `None` means "leave alone"."""

    plan: str | None = None
    is_active: bool | None = None
