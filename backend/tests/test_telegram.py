"""Telegram channel tests: sender, plan gating, the connect-link flow, webhook, and delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.api.v1.endpoints import settings as settings_endpoint
from app.api.v1.endpoints import telegram as telegram_endpoint
from app.core.constants import channel_allowed
from app.main import app
from app.models.notification_channel import NotificationChannel
from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from app.notifiers.telegram import TelegramNotifier, render_text
from app.services.telegram import hash_token
from app.workers import notify
from tests.test_notify import FakeNotifier, confirmed_match, deliveries, fake_ctx, make_user

SECRET = "hook_secret-123"
BOT_TOKEN = "123456:SECRET_BOT_TOKEN"
MESSAGE = NotificationMessage(
    watcher_name="dev <hiring>",
    subreddit="forhire",
    title="Need a <b>dev</b> & more",
    snippet="Looking for help",
    reason="Poster is hiring",
    post_url="https://reddit.com/r/forhire/abc",
    feed_url="http://localhost:3000/matches",
)


# --- pure tests ---------------------------------------------------------------------------------


def test_render_text_escapes_post_content():
    text = render_text(MESSAGE)
    assert "<b>dev</b>" not in text
    assert "Need a &lt;b&gt;dev&lt;/b&gt; &amp; more" in text
    assert "dev &lt;hiring&gt;" in text


@pytest.mark.parametrize(
    ("plan", "channel", "allowed"),
    [
        ("free", "email", True),
        ("free", "slack", True),
        ("free", "telegram", False),
        ("standard", "telegram", True),
        ("premium", "telegram", True),
        ("enterprise", "telegram", True),
        ("typo-plan", "telegram", False),
    ],
)
def test_channel_allowed_by_plan(plan, channel, allowed):
    assert channel_allowed(plan, channel) is allowed


def telegram_notifier(status: int = 200) -> tuple[TelegramNotifier, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"ok": status == 200})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramNotifier(BOT_TOKEN, client=client), seen


async def test_telegram_notifier_sends_html_to_the_chat():
    notifier, seen = telegram_notifier()

    await notifier.send("555", MESSAGE)

    assert str(seen[0].url) == f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    assert b'"chat_id":"555"' in seen[0].content.replace(b" ", b"")
    assert b"HTML" in seen[0].content


@pytest.mark.parametrize("status", [429, 500, 502, 401])
async def test_telegram_notifier_temporary_errors(status):
    notifier, _ = telegram_notifier(status)
    with pytest.raises(TemporaryDeliveryError):
        await notifier.send("555", MESSAGE)


@pytest.mark.parametrize("status", [400, 403, 404])
async def test_telegram_notifier_permanent_errors(status):
    notifier, _ = telegram_notifier(status)
    with pytest.raises(PermanentDeliveryError):
        await notifier.send("555", MESSAGE)


async def test_a_network_error_never_leaks_the_bot_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    notifier = TelegramNotifier(
        BOT_TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TemporaryDeliveryError) as raised:
        await notifier.send("555", MESSAGE)

    assert BOT_TOKEN not in str(raised.value)


# --- connect link + webhook (DB) ----------------------------------------------------------------


@pytest.fixture
def telegram_env(monkeypatch):
    """Configure Telegram for the API and capture what the bot would send back to users."""
    notifier, seen = telegram_notifier()

    async def override():
        yield {"telegram": notifier, "slack": FakeNotifier()}

    app.dependency_overrides[settings_endpoint.get_notifiers] = override
    config = SimpleNamespace(
        TELEGRAM_BOT_TOKEN=BOT_TOKEN,
        TELEGRAM_BOT_USERNAME="PostPingBot",
        TELEGRAM_WEBHOOK_SECRET=SECRET,
        TELEGRAM_LINK_TTL_MINUTES=15,
    )
    monkeypatch.setattr(settings_endpoint, "get_settings", lambda: config)
    monkeypatch.setattr(telegram_endpoint, "get_settings", lambda: config)
    return SimpleNamespace(requests=seen, config=config)


def replies(env) -> list[str]:
    return [request.content.decode() for request in env.requests]


async def get_telegram_row(session, user) -> NotificationChannel | None:
    result = await session.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user.id,
            NotificationChannel.channel_type == "telegram",
        )
    )
    return result.scalar_one_or_none()


async def issue_link(auth_client) -> str:
    response = await auth_client.post("/api/v1/settings/channels/telegram/link")
    assert response.status_code == 200, response.text
    return response.json()["url"].split("start=")[1]


async def press_start(auth_client, token: str, chat_id: int = 777, chat_type: str = "private"):
    return await auth_client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"text": f"/start {token}", "chat": {"id": chat_id, "type": chat_type}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )


@pytest.mark.db
async def test_free_plan_cannot_create_a_telegram_link(auth_client, telegram_env):
    response = await auth_client.post("/api/v1/settings/channels/telegram/link")

    assert response.status_code == 403
    assert "paid" in response.json()["detail"]


@pytest.mark.db
async def test_link_is_a_503_when_telegram_is_not_configured(auth_client, db_user, db_session):
    db_user.plan = "standard"
    await db_session.commit()

    response = await auth_client.post("/api/v1/settings/channels/telegram/link")

    assert response.status_code == 503


@pytest.mark.db
async def test_paid_user_gets_a_link_and_a_pending_unverified_channel(
    auth_client, db_session, db_user, telegram_env
):
    db_user.plan = "standard"
    await db_session.commit()

    response = await auth_client.post("/api/v1/settings/channels/telegram/link")

    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://t.me/PostPingBot?start=")
    assert body["expires_in_minutes"] == 15
    token = body["url"].split("start=")[1]

    row = await get_telegram_row(db_session, db_user)
    assert row.verified is False
    assert row.link_pending is True
    # Only a hash is stored — the token itself must not sit in the database.
    assert token not in str(row.config)
    assert row.config["link_token_hash"] == hash_token(token)

    settings = await auth_client.get("/api/v1/settings")
    telegram = next(c for c in settings.json()["channels"] if c["channel_type"] == "telegram")
    assert telegram["link_pending"] is True and telegram["verified"] is False


@pytest.mark.db
async def test_pressing_start_connects_the_chat_and_consumes_the_token(
    auth_client, db_session, db_user, telegram_env
):
    db_user.plan = "standard"
    await db_session.commit()
    token = await issue_link(auth_client)

    response = await press_start(auth_client, token, chat_id=777)

    assert response.status_code == 200
    row = await get_telegram_row(db_session, db_user)
    await db_session.refresh(row)
    assert (row.verified, row.enabled) == (True, True)
    assert row.config == {"destination": "777"}
    assert row.link_pending is False
    assert any("connected" in reply for reply in replies(telegram_env))

    # The same link can't be used a second time.
    again = await press_start(auth_client, token, chat_id=999)
    assert again.status_code == 200
    await db_session.refresh(row)
    assert row.config == {"destination": "777"}
    assert any("expired or was already used" in reply for reply in replies(telegram_env))


@pytest.mark.db
async def test_an_expired_link_does_not_connect(auth_client, db_session, db_user, telegram_env):
    db_user.plan = "standard"
    await db_session.commit()
    token = await issue_link(auth_client)
    row = await get_telegram_row(db_session, db_user)
    row.config = {
        **row.config,
        "link_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    await db_session.commit()

    await press_start(auth_client, token)

    await db_session.refresh(row)
    assert row.verified is False
    assert "destination" not in row.config


@pytest.mark.db
async def test_group_chats_and_unknown_tokens_never_connect(
    auth_client, db_session, db_user, telegram_env
):
    db_user.plan = "standard"
    await db_session.commit()
    token = await issue_link(auth_client)

    await press_start(auth_client, token, chat_type="group")
    await press_start(auth_client, "not-a-real-token")

    row = await get_telegram_row(db_session, db_user)
    await db_session.refresh(row)
    assert row.verified is False


@pytest.mark.db
async def test_bare_start_tells_the_user_how_to_connect(auth_client, telegram_env):
    response = await auth_client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"text": "/start", "chat": {"id": 5, "type": "private"}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status_code == 200
    assert any("Connect Telegram" in reply for reply in replies(telegram_env))


@pytest.mark.db
async def test_webhook_rejects_a_missing_or_wrong_secret(auth_client, telegram_env):
    body = {"message": {"text": "/start x", "chat": {"id": 1, "type": "private"}}}

    assert (await auth_client.post("/api/v1/telegram/webhook", json=body)).status_code == 403
    wrong = await auth_client.post(
        "/api/v1/telegram/webhook", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}
    )
    assert wrong.status_code == 403
    assert telegram_env.requests == []


@pytest.mark.db
async def test_webhook_is_a_503_when_no_secret_is_configured(auth_client, telegram_env):
    telegram_env.config.TELEGRAM_WEBHOOK_SECRET = ""

    response = await auth_client.post(
        "/api/v1/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""}
    )

    assert response.status_code == 503


@pytest.mark.db
async def test_replacing_a_connected_chat_keeps_alerts_flowing_until_start_is_pressed(
    auth_client, db_session, db_user, telegram_env
):
    db_user.plan = "standard"
    await db_session.commit()
    await press_start(auth_client, await issue_link(auth_client), chat_id=111)

    new_token = await issue_link(auth_client)

    row = await get_telegram_row(db_session, db_user)
    await db_session.refresh(row)
    assert (row.verified, row.config["destination"]) == (True, "111")
    await press_start(auth_client, new_token, chat_id=222)
    await db_session.refresh(row)
    assert row.config == {"destination": "222"}


@pytest.mark.db
async def test_test_message_is_blocked_on_a_free_plan(auth_client, telegram_env):
    response = await auth_client.post("/api/v1/settings/channels/telegram/test")

    assert response.status_code == 403


# --- worker delivery (DB) -----------------------------------------------------------------------


async def connect_telegram_row(session, user, verified=True, enabled=True) -> NotificationChannel:
    channel = NotificationChannel(
        user_id=user.id,
        channel_type="telegram",
        enabled=enabled,
        verified=verified,
        config={"destination": "777"},
    )
    session.add(channel)
    await session.commit()
    return channel


def telegram_ctx(notifier: FakeNotifier) -> dict:
    ctx = fake_ctx(None)
    notifier.channel_type = "telegram"
    ctx["notifiers"] = {"telegram": notifier}
    return ctx


@pytest.mark.db
async def test_paid_users_receive_matches_on_telegram(db_session, use_test_session):
    user = await make_user(db_session)
    user.plan = "standard"
    await connect_telegram_row(db_session, user)
    row = await confirmed_match(db_session, user)
    telegram = FakeNotifier()

    sent = await notify.notify_match(telegram_ctx(telegram), str(row.id))

    assert sent == 1
    assert telegram.sent[0][0] == "777"
    [delivery] = await deliveries(db_session, row.id)
    assert (delivery.channel_type, delivery.status) == ("telegram", "sent")


@pytest.mark.db
async def test_a_downgraded_user_stops_receiving_telegram_alerts(db_session, use_test_session):
    user = await make_user(db_session)  # free plan, but a leftover connected Telegram row
    await connect_telegram_row(db_session, user)
    row = await confirmed_match(db_session, user)
    telegram = FakeNotifier()

    sent = await notify.notify_match(telegram_ctx(telegram), str(row.id))

    assert sent == 0
    assert telegram.sent == []
    assert await deliveries(db_session, row.id) == []


@pytest.mark.db
async def test_telegram_is_skipped_until_the_chat_is_verified(db_session, use_test_session):
    user = await make_user(db_session)
    user.plan = "standard"
    await connect_telegram_row(db_session, user, verified=False)
    row = await confirmed_match(db_session, user)
    telegram = FakeNotifier()

    assert await notify.notify_match(telegram_ctx(telegram), str(row.id)) == 0
    assert telegram.sent == []


@pytest.mark.db
async def test_a_blocked_bot_flags_the_channel_for_reconnect(db_session, use_test_session):
    user = await make_user(db_session)
    user.plan = "standard"
    channel = await connect_telegram_row(db_session, user)
    row = await confirmed_match(db_session, user)
    telegram = FakeNotifier(error=PermanentDeliveryError("telegram 403: bot was blocked"))

    await notify.notify_match(telegram_ctx(telegram), str(row.id))

    await db_session.refresh(channel)
    assert channel.verified is False
    [delivery] = await deliveries(db_session, row.id)
    assert delivery.status == "failed"
