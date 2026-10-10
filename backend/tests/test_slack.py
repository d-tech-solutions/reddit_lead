"""Slack channel tests: the sender (pure), the connect/test/disconnect API, and worker delivery."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.api.v1.endpoints import settings as settings_endpoint
from app.core.crypto import (
    EncryptionNotConfigured,
    UndecryptableSecret,
    decrypt_secret,
    encrypt_secret,
)
from app.main import app
from app.models.notification_channel import NotificationChannel
from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from app.notifiers.slack import SlackNotifier, escape_mrkdwn, is_valid_webhook_url, render_payload
from app.workers import notify
from tests.test_notify import (
    TEST_KEY,
    FakeNotifier,
    confirmed_match,
    deliveries,
    fake_ctx,
    make_user,
)

WEBHOOK = "https://hooks.slack.com/services/T000/B000/abcDEF123"
KEY = Fernet.generate_key().decode()

MESSAGE = NotificationMessage(
    watcher_name="dev hiring",
    subreddit="forhire",
    title="Need <@U1> & a dev",
    snippet="Looking for help",
    reason="Poster is hiring",
    post_url="https://reddit.com/r/forhire/abc",
    feed_url="http://localhost:3000/matches",
)


# --- pure tests ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        (WEBHOOK, True),
        ("https://hooks.slack.com/workflows/T000/A000/123/abc", True),
        ("http://hooks.slack.com/services/T/B/x", False),
        ("https://hooks.slack.com.evil.com/services/T/B/x", False),
        ("https://evil.com/https://hooks.slack.com/services/T/B/x", False),
        ("https://hooks.slack.com/services/T/B/x?redirect=http://internal", False),
        ("http://169.254.169.254/latest/meta-data", False),
        ("", False),
    ],
)
def test_webhook_url_validation(url, valid):
    assert is_valid_webhook_url(url) is valid


def test_slack_text_is_escaped_so_post_content_cannot_ping_or_inject_links():
    assert escape_mrkdwn("<!channel> a & b") == "&lt;!channel&gt; a &amp; b"
    payload = render_payload(MESSAGE)
    assert "<@U1>" not in str(payload)
    assert "&lt;@U1&gt; &amp; a dev" in str(payload)


def slack_notifier(status: int) -> tuple[SlackNotifier, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text="ok" if status == 200 else "error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SlackNotifier(client=client), seen


async def test_slack_notifier_posts_blocks_to_the_webhook():
    notifier, seen = slack_notifier(200)

    await notifier.send(WEBHOOK, MESSAGE)

    assert str(seen[0].url) == WEBHOOK
    assert b"blocks" in seen[0].content


@pytest.mark.parametrize("status", [429, 500, 502])
async def test_slack_notifier_treats_rate_limits_and_server_errors_as_temporary(status):
    notifier, _ = slack_notifier(status)
    with pytest.raises(TemporaryDeliveryError):
        await notifier.send(WEBHOOK, MESSAGE)


@pytest.mark.parametrize("status", [302, 400, 403, 404, 410])
async def test_slack_notifier_treats_everything_else_as_permanent(status):
    notifier, _ = slack_notifier(status)
    with pytest.raises(PermanentDeliveryError):
        await notifier.send(WEBHOOK, MESSAGE)


async def test_slack_notifier_refuses_a_non_slack_destination_without_any_request():
    notifier, seen = slack_notifier(200)
    with pytest.raises(PermanentDeliveryError):
        await notifier.send("http://169.254.169.254/", MESSAGE)
    assert seen == []


def test_crypto_roundtrip_and_failure_modes():
    token = encrypt_secret(KEY, WEBHOOK)
    assert token != WEBHOOK
    assert decrypt_secret(KEY, token) == WEBHOOK
    with pytest.raises(UndecryptableSecret):
        decrypt_secret(Fernet.generate_key().decode(), token)
    with pytest.raises(EncryptionNotConfigured):
        encrypt_secret("", WEBHOOK)
    with pytest.raises(EncryptionNotConfigured):
        encrypt_secret("not-a-key", WEBHOOK)


# --- API tests (DB) -----------------------------------------------------------------------------


@pytest.fixture
def slack_notifier_override(monkeypatch):
    """Swap the test-send notifier for a fake and give the API an encryption key."""
    fake = FakeNotifier()
    fake.channel_type = "slack"

    async def override():
        yield {"slack": fake, "email": FakeNotifier()}

    app.dependency_overrides[settings_endpoint.get_notifiers] = override
    monkeypatch.setattr(
        settings_endpoint, "get_settings", lambda: SimpleNamespace(NOTIFY_ENCRYPTION_KEY=KEY)
    )
    return fake


@pytest.mark.db
async def test_connect_slack_sends_a_test_then_stores_the_webhook_encrypted(
    auth_client, db_session, db_user, slack_notifier_override
):
    response = await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})

    assert response.status_code == 200
    assert slack_notifier_override.sent[0][0] == WEBHOOK
    slack = next(c for c in response.json()["channels"] if c["channel_type"] == "slack")
    assert slack == {
        "channel_type": "slack",
        "enabled": True,
        "verified": True,
        "link_pending": False,
    }
    # The webhook must never come back out of the API.
    assert "hooks.slack.com" not in response.text

    row = (
        await db_session.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == db_user.id,
                NotificationChannel.channel_type == "slack",
            )
        )
    ).scalar_one()
    assert WEBHOOK not in str(row.config)
    assert decrypt_secret(KEY, row.config["webhook_url_encrypted"]) == WEBHOOK


@pytest.mark.db
async def test_connect_slack_rejects_a_non_slack_url(auth_client, slack_notifier_override):
    response = await auth_client.put(
        "/api/v1/settings/channels/slack", json={"webhook_url": "https://evil.com/hook"}
    )

    assert response.status_code == 422
    assert slack_notifier_override.sent == []


@pytest.mark.db
async def test_connect_slack_does_not_save_when_slack_rejects_the_webhook(
    auth_client, db_session, db_user, slack_notifier_override
):
    slack_notifier_override.error = PermanentDeliveryError("slack 404: no_service")

    response = await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})

    assert response.status_code == 400
    rows = (
        await db_session.execute(
            select(NotificationChannel).where(NotificationChannel.user_id == db_user.id)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.db
async def test_connect_slack_without_an_encryption_key_is_a_503(auth_client, monkeypatch):
    monkeypatch.setattr(
        settings_endpoint, "get_settings", lambda: SimpleNamespace(NOTIFY_ENCRYPTION_KEY="", RESEND_API_KEY="", NOTIFY_FROM_EMAIL="", TELEGRAM_BOT_TOKEN="")
    )

    response = await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})

    assert response.status_code == 503


@pytest.mark.db
async def test_reconnecting_clears_a_needs_reconnect_flag(
    auth_client, db_session, db_user, slack_notifier_override
):
    await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})
    row = (
        await db_session.execute(
            select(NotificationChannel).where(NotificationChannel.channel_type == "slack")
        )
    ).scalar_one()
    row.verified = False
    await db_session.commit()

    await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})

    await db_session.refresh(row)
    assert row.verified is True


@pytest.mark.db
async def test_toggle_and_disconnect_slack(auth_client, db_session, slack_notifier_override):
    await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})

    off = await auth_client.patch("/api/v1/settings/channels/slack", json={"enabled": False})
    assert next(c for c in off.json()["channels"] if c["channel_type"] == "slack")["enabled"] is False

    gone = await auth_client.delete("/api/v1/settings/channels/slack")
    assert gone.status_code == 204
    after = await auth_client.get("/api/v1/settings")
    assert [c["channel_type"] for c in after.json()["channels"]] == ["email"]


@pytest.mark.db
async def test_email_cannot_be_disconnected_and_unknown_channels_404(auth_client):
    await auth_client.get("/api/v1/settings")

    assert (await auth_client.delete("/api/v1/settings/channels/email")).status_code == 400
    assert (await auth_client.delete("/api/v1/settings/channels/slack")).status_code == 404
    assert (
        await auth_client.patch("/api/v1/settings/channels/nope", json={"enabled": True})
    ).status_code == 404


@pytest.mark.db
async def test_send_test_notification_uses_the_saved_webhook(
    auth_client, slack_notifier_override
):
    await auth_client.put("/api/v1/settings/channels/slack", json={"webhook_url": WEBHOOK})
    slack_notifier_override.sent.clear()

    response = await auth_client.post("/api/v1/settings/channels/slack/test")

    assert response.status_code == 204
    assert slack_notifier_override.sent[0][0] == WEBHOOK


@pytest.mark.db
async def test_send_test_notification_for_an_unconnected_channel_is_a_404(
    auth_client, slack_notifier_override
):
    response = await auth_client.post("/api/v1/settings/channels/slack/test")

    assert response.status_code == 404


# --- worker delivery (DB) -----------------------------------------------------------------------


async def connect_slack_row(session, user, enabled=True, verified=True) -> NotificationChannel:
    channel = NotificationChannel(
        user_id=user.id,
        channel_type="slack",
        enabled=enabled,
        verified=verified,
        config={"webhook_url_encrypted": encrypt_secret(TEST_KEY, WEBHOOK)},
    )
    session.add(channel)
    await session.commit()
    return channel


def slack_ctx(slack: FakeNotifier, **kwargs) -> dict:
    ctx = fake_ctx(None, **kwargs)
    slack.channel_type = "slack"
    ctx["notifiers"] = {"slack": slack}
    return ctx


@pytest.mark.db
async def test_notify_match_delivers_to_slack_with_the_decrypted_webhook(
    db_session, use_test_session
):
    user = await make_user(db_session)
    await connect_slack_row(db_session, user)
    row = await confirmed_match(db_session, user)
    slack = FakeNotifier()

    sent = await notify.notify_match(slack_ctx(slack), str(row.id))

    assert sent == 1
    assert slack.sent[0][0] == WEBHOOK
    [delivery] = await deliveries(db_session, row.id)
    assert (delivery.channel_type, delivery.status) == ("slack", "sent")


@pytest.mark.db
async def test_slack_is_not_used_when_not_connected_disabled_or_needing_reconnect(
    db_session, use_test_session
):
    user = await make_user(db_session)
    slack = FakeNotifier()
    row = await confirmed_match(db_session, user)

    # Not connected: no row at all (and, unlike email, no implicit default).
    assert await notify.notify_match(slack_ctx(slack), str(row.id)) == 0

    channel = await connect_slack_row(db_session, user, enabled=False)
    assert await notify.notify_match(slack_ctx(slack), str(row.id)) == 0

    channel.enabled = True
    channel.verified = False
    await db_session.commit()
    assert await notify.notify_match(slack_ctx(slack), str(row.id)) == 0
    assert slack.sent == []


@pytest.mark.db
async def test_a_dead_webhook_flags_the_channel_for_reconnect(db_session, use_test_session):
    user = await make_user(db_session)
    channel = await connect_slack_row(db_session, user)
    row = await confirmed_match(db_session, user)
    slack = FakeNotifier(error=PermanentDeliveryError("slack 404: no_service"))

    await notify.notify_match(slack_ctx(slack), str(row.id))

    await db_session.refresh(channel)
    assert channel.verified is False
    [delivery] = await deliveries(db_session, row.id)
    assert delivery.status == "failed"


@pytest.mark.db
async def test_an_undecryptable_webhook_fails_the_delivery_and_flags_the_channel(
    db_session, use_test_session
):
    user = await make_user(db_session)
    channel = await connect_slack_row(db_session, user)
    channel.config = {"webhook_url_encrypted": encrypt_secret(KEY, WEBHOOK)}  # a different key
    await db_session.commit()
    row = await confirmed_match(db_session, user)
    slack = FakeNotifier()

    await notify.notify_match(slack_ctx(slack), str(row.id))

    assert slack.sent == []
    await db_session.refresh(channel)
    assert channel.verified is False
    [delivery] = await deliveries(db_session, row.id)
    assert delivery.status == "failed"
