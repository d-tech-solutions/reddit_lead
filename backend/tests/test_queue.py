"""The API's best-effort catch-up enqueue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.config import MATCH_QUEUE
from app.services import queue


class FakePool:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[tuple, dict]] = []

    async def enqueue_job(self, *args, **kwargs):
        if self.error:
            raise self.error
        self.calls.append((args, kwargs))


async def test_enqueue_catchup_sends_the_window_end_and_a_deduping_job_id(monkeypatch):
    pool = FakePool()

    async def fake_get_pool():
        return pool

    monkeypatch.setattr(queue, "_get_pool", fake_get_pool)
    watcher_id = uuid.uuid4()
    until = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    await queue.enqueue_catchup(watcher_id, ["forhire"], until)

    [(args, kwargs)] = pool.calls
    assert args == ("catchup_watcher", str(watcher_id), ["forhire"], until.isoformat())
    assert kwargs["_job_id"] == f"catchup:{watcher_id}:{int(until.timestamp())}"
    assert kwargs["_queue_name"] == MATCH_QUEUE


async def test_enqueue_catchup_swallows_a_redis_outage(monkeypatch):
    async def fake_get_pool():
        return FakePool(error=RuntimeError("redis is down"))

    monkeypatch.setattr(queue, "_get_pool", fake_get_pool)

    await queue.enqueue_catchup(uuid.uuid4(), ["forhire"], datetime.now(UTC))


async def test_enqueue_catchup_with_no_subreddits_does_nothing(monkeypatch):
    async def fail():
        raise AssertionError("must not connect")

    monkeypatch.setattr(queue, "_get_pool", fail)

    await queue.enqueue_catchup(uuid.uuid4(), [], datetime.now(UTC))
