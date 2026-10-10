"""Notify worker and email notifier tests.

The notifier tests are pure (httpx's MockTransport stands in for Resend). The worker tests run
against a real, rolled-back Postgres, same convention as test_match.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from arq import Retry
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MATCH_QUEUE, NOTIFY_QUEUE
from app.models.match import Match
from app.models.notification_channel import NotificationChannel
from app.models.notification_delivery import NotificationDelivery
from app.models.user import User
from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
    make_snippet,
)
from app.notifiers.email import EmailNotifier, render_html
from app.workers import match as match_worker
from app.workers import notify, outcomes
from tests.test_match import make_db_watcher, make_matched_post, make_user

TEST_KEY = Fernet.generate_key().decode()

MESSAGE = NotificationMessage(
    watcher_name="dev hiring",
    subreddit="forhire",
    title="Need a <b>developer</b>",
    snippet="Looking for help",
    reason="Poster is hiring",
    post_url="https://reddit.com/r/forhire/abc",
    feed_url="http://localhost:3000/matches",
)


# --- pure tests ---------------------------------------------------------------------------------


def test_make_snippet_collapses_whitespace_and_truncates():
    assert make_snippet("a  b\n\nc") == "a b c"
    long = make_snippet("word " * 200)
    assert len(long) <= 280
    assert long.endswith("…")


def test_render_html_escapes_post_content():
    html = render_html(MESSAGE)
    assert "<b>developer</b>" not in html
    assert "&lt;b&gt;developer&lt;/b&gt;" in html


def email_notifier(status: int) -> tuple[EmailNotifier, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"id": "x"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return EmailNotifier("re_key", "PostPing <a@b.c>", client=client), seen


async def test_email_notifier_posts_to_resend():
    notifier, seen = email_notifier(200)

    await notifier.send("me@example.com", MESSAGE)

    assert seen[0].headers["Authorization"] == "Bearer re_key"
    assert b"me@example.com" in seen[0].content


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_email_notifier_treats_rate_limits_and_server_errors_as_temporary(status):
    notifier, _ = email_notifier(status)
    with pytest.raises(TemporaryDeliveryError):
        await notifier.send("me@example.com", MESSAGE)


@pytest.mark.parametrize("status", [400, 401, 403, 422])
async def test_email_notifier_treats_client_errors_as_permanent(status):
    notifier, _ = email_notifier(status)
    with pytest.raises(PermanentDeliveryError):
        await notifier.send("me@example.com", MESSAGE)


# --- worker tests (DB) --------------------------------------------------------------------------


class FakeNotifier:
    channel_type = "email"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[tuple[str, NotificationMessage]] = []

    async def send(self, destination: str, message: NotificationMessage) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append((destination, message))

    async def close(self) -> None:
        pass


def fake_ctx(notifier: FakeNotifier | None, max_attempts: int = 4) -> dict:
    settings = SimpleNamespace(
        FRONTEND_URL="http://localhost:3000",
        NOTIFY_MAX_ATTEMPTS=max_attempts,
        NOTIFY_ENCRYPTION_KEY=TEST_KEY,
        NOTIFY_BACKFILL_WINDOW_HOURS=6,
        NOTIFY_BACKFILL_LIMIT=200,
    )
    return {"settings": settings, "notifiers": {"email": notifier} if notifier else {}}


async def confirmed_match(
    session: AsyncSession, user: User, *, created_at: datetime | None = None, **watcher_kwargs
) -> Match:
    watcher = await make_db_watcher(session, user, **watcher_kwargs)
    post = await make_matched_post(session)
    row = Match(
        watcher_id=watcher.id,
        matched_post_id=post.id,
        llm_reason="clear request",
        created_at=created_at or datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def deliveries(session: AsyncSession, match_id: uuid.UUID) -> list[NotificationDelivery]:
    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.match_id == match_id)
    )
    return list(result.scalars())


@pytest.mark.db
async def test_notify_match_sends_email_to_the_account_address_by_default(
    db_session, use_test_session
):
    user = await make_user(db_session)
    user.email = "account@example.com"
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier()

    sent = await notify.notify_match(fake_ctx(notifier), str(row.id))

    assert sent == 1
    assert notifier.sent[0][0] == "account@example.com"
    assert notifier.sent[0][1].reason == "clear request"
    [delivery] = await deliveries(db_session, row.id)
    assert (delivery.status, delivery.attempts) == ("sent", 1)
    await db_session.refresh(row)
    assert row.notified_at is not None


@pytest.mark.db
async def test_notify_match_prefers_the_notification_email_override(db_session, use_test_session):
    user = await make_user(db_session)
    user.email = "account@example.com"
    user.notification_email = "alerts@example.com"
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier()

    await notify.notify_match(fake_ctx(notifier), str(row.id))

    assert notifier.sent[0][0] == "alerts@example.com"


@pytest.mark.db
async def test_notify_match_never_sends_the_same_match_twice(db_session, use_test_session):
    user = await make_user(db_session)
    user.email = "account@example.com"
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier()

    await notify.notify_match(fake_ctx(notifier), str(row.id))
    second = await notify.notify_match(fake_ctx(notifier), str(row.id))

    assert second == 0
    assert len(notifier.sent) == 1


@pytest.mark.db
async def test_notify_match_respects_a_disabled_email_channel(db_session, use_test_session):
    user = await make_user(db_session)
    user.email = "account@example.com"
    db_session.add(NotificationChannel(user_id=user.id, channel_type="email", enabled=False))
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier()

    sent = await notify.notify_match(fake_ctx(notifier), str(row.id))

    assert sent == 0
    assert notifier.sent == []
    assert await deliveries(db_session, row.id) == []


@pytest.mark.db
async def test_notify_match_skips_when_there_is_no_address(db_session, use_test_session):
    user = await make_user(db_session)  # no email at all
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier()

    await notify.notify_match(fake_ctx(notifier), str(row.id))

    [delivery] = await deliveries(db_session, row.id)
    assert delivery.status == "skipped"
    assert notifier.sent == []


@pytest.mark.db
async def test_notify_match_ignores_paused_watchers_and_unknown_matches(
    db_session, use_test_session
):
    user = await make_user(db_session)
    user.email = "account@example.com"
    paused = await confirmed_match(db_session, user, status="paused")
    notifier = FakeNotifier()

    assert await notify.notify_match(fake_ctx(notifier), str(paused.id)) == 0
    assert await notify.notify_match(fake_ctx(notifier), str(uuid.uuid4())) == 0
    assert notifier.sent == []


@pytest.mark.db
async def test_temporary_failure_asks_arq_to_retry_then_gives_up(db_session, use_test_session):
    user = await make_user(db_session)
    user.email = "account@example.com"
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier(error=TemporaryDeliveryError("429"))
    ctx = fake_ctx(notifier, max_attempts=2)

    with pytest.raises(Retry):
        await notify.notify_match(ctx, str(row.id))
    [delivery] = await deliveries(db_session, row.id)
    assert (delivery.status, delivery.attempts) == ("pending", 1)

    # Second attempt hits the cap: marked failed, no further retry requested.
    await notify.notify_match(ctx, str(row.id))
    await db_session.refresh(delivery)
    assert (delivery.status, delivery.attempts) == ("failed", 2)


@pytest.mark.db
async def test_permanent_failure_fails_immediately(db_session, use_test_session):
    user = await make_user(db_session)
    user.email = "account@example.com"
    row = await confirmed_match(db_session, user)
    notifier = FakeNotifier(error=PermanentDeliveryError("bad address"))

    await notify.notify_match(fake_ctx(notifier), str(row.id))

    [delivery] = await deliveries(db_session, row.id)
    assert delivery.status == "failed"
    assert "bad address" in delivery.last_error


@pytest.mark.db
async def test_pending_sweep_finds_recent_unnotified_matches_only(db_session):
    user = await make_user(db_session)
    fresh = await confirmed_match(db_session, user, name="fresh")
    await confirmed_match(
        db_session, user, name="old", created_at=datetime.now(UTC) - timedelta(hours=48)
    )
    done = await confirmed_match(db_session, user, name="done")
    done.notified_at = datetime.now(UTC)
    gave_up = await confirmed_match(db_session, user, name="gave-up")
    db_session.add(
        NotificationDelivery(match_id=gave_up.id, channel_type="email", status="failed", attempts=4)
    )
    await db_session.commit()

    ids = await notify.fetch_pending_match_ids(db_session, window_hours=6, limit=50)

    assert ids == [fresh.id]


class FakeRedis:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str, str]] = []
        self.queues: list[str] = []

    async def enqueue_job(self, name: str, arg: str, _job_id: str, _queue_name: str) -> None:
        self.jobs.append((name, arg, _job_id))
        self.queues.append(_queue_name)


async def test_enqueue_notifications_queues_a_job_per_match():
    first, second = uuid.uuid4(), uuid.uuid4()
    redis = FakeRedis()

    await outcomes.enqueue_notifications(redis, [first, second])

    # The job id is derived from the match id so a duplicate enqueue is a no-op.
    assert redis.jobs == [
        ("notify_match", str(first), f"notify_match:{first}"),
        ("notify_match", str(second), f"notify_match:{second}"),
    ]
    assert redis.queues == [NOTIFY_QUEUE, NOTIFY_QUEUE]


async def test_enqueue_notifications_survives_a_failing_queue():
    class BrokenRedis:
        async def enqueue_job(self, *args, **kwargs):
            raise RuntimeError("redis is down")

    await outcomes.enqueue_notifications(BrokenRedis(), [uuid.uuid4()])


def test_workers_consume_separate_queues():
    assert match_worker.WorkerSettings.queue_name == MATCH_QUEUE
    assert notify.WorkerSettings.queue_name == NOTIFY_QUEUE
    assert MATCH_QUEUE != NOTIFY_QUEUE


async def test_enqueue_notifications_without_redis_is_a_noop():
    await outcomes.enqueue_notifications(None, [uuid.uuid4()])
