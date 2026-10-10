"""Endpoint tests against a real Postgres.

Marked `db` and skipped automatically when Postgres is unreachable — see tests/conftest.py.
Everything runs inside a transaction that is rolled back, so these are safe against a shared
development database.
"""

import pytest
from sqlalchemy import select

from app.models.notification_channel import NotificationChannel

pytestmark = pytest.mark.db


async def test_get_creates_the_default_email_channel(auth_client, db_session, db_user):
    response = await auth_client.get("/api/v1/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["account_email"] == db_user.email
    assert body["notification_email"] is None
    assert body["channels"] == [
        {"channel_type": "email", "enabled": True, "verified": True, "link_pending": False}
    ]

    result = await db_session.execute(
        select(NotificationChannel).where(NotificationChannel.user_id == db_user.id)
    )
    assert result.scalar_one().channel_type == "email"


async def test_get_is_idempotent(auth_client, db_session, db_user):
    await auth_client.get("/api/v1/settings")
    await auth_client.get("/api/v1/settings")

    result = await db_session.execute(
        select(NotificationChannel).where(NotificationChannel.user_id == db_user.id)
    )
    assert len(result.scalars().all()) == 1


async def test_patch_sets_notification_email_and_disables_email(auth_client, db_session, db_user):
    response = await auth_client.patch(
        "/api/v1/settings",
        json={"notification_email": "leads@example.com", "email_enabled": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["notification_email"] == "leads@example.com"
    assert body["channels"][0]["enabled"] is False

    await db_session.refresh(db_user)
    assert db_user.notification_email == "leads@example.com"


async def test_patch_with_blank_email_clears_the_override(auth_client, db_user):
    await auth_client.patch(
        "/api/v1/settings",
        json={"notification_email": "leads@example.com", "email_enabled": True},
    )

    response = await auth_client.patch(
        "/api/v1/settings", json={"notification_email": "  ", "email_enabled": True}
    )

    assert response.status_code == 200
    assert response.json()["notification_email"] is None
