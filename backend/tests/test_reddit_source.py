from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.workers.reddit_source import (
    RssSource,
    _parse_rss_entry,
    _parse_submission,
    _within_window,
    build_source,
)


def test_parse_rss_entry_strips_t3_prefix_and_username_slash():
    entry = SimpleNamespace(
        id="t3_abc123",
        title="Looking for a plumber",
        author="/u/someone",
        link="https://www.reddit.com/r/test/comments/abc123/x/",
        updated="2026-07-26T10:00:00+00:00",
    )

    post = _parse_rss_entry(entry, "test")

    assert post["reddit_post_id"] == "abc123"
    assert post["subreddit"] == "test"
    assert post["title"] == "Looking for a plumber"
    assert post["author"] == "someone"
    assert post["body"] == ""
    assert post["posted_at"] == datetime(2026, 7, 26, 10, 0, tzinfo=UTC)


def test_parse_rss_entry_tolerates_unparseable_date():
    entry = SimpleNamespace(id="t3_abc123", title="x", link="y", updated="not-a-date")

    assert _parse_rss_entry(entry, "test")["posted_at"] is None


def test_parse_rss_entry_returns_none_without_id():
    assert _parse_rss_entry(SimpleNamespace(id="", title="x", link="y"), "test") is None


def test_parse_submission_maps_api_fields():
    submission = SimpleNamespace(
        id="xyz789",
        title="Need a logo designed",
        selftext="Details here",
        author="reddituser",
        permalink="/r/test/comments/xyz789/x/",
        created_utc=1785000000,
    )

    post = _parse_submission(submission, "test")

    assert post["reddit_post_id"] == "xyz789"
    assert post["body"] == "Details here"
    assert post["author"] == "reddituser"
    assert post["permalink"] == "https://www.reddit.com/r/test/comments/xyz789/x/"
    assert post["posted_at"] == datetime.fromtimestamp(1785000000, tz=UTC)


def test_parse_submission_handles_deleted_author():
    submission = SimpleNamespace(
        id="xyz789", title="t", selftext="", author=None, permalink="/p", created_utc=None
    )

    post = _parse_submission(submission, "test")

    assert post["author"] is None
    assert post["posted_at"] is None


def test_build_source_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unknown REDDIT_FETCH_MODE"):
        build_source("carrier-pigeon", "", "", "agent")


def test_build_source_rejects_api_mode_without_credentials():
    with pytest.raises(ValueError, match="REDDIT_CLIENT_ID"):
        build_source("api", "", "", "agent")


# --- fetch_window ---------------------------------------------------------------------------------


def _window_post(post_id: str, posted_at):
    return {"reddit_post_id": post_id, "posted_at": posted_at}


def test_within_window_keeps_recent_and_untimed_posts():
    since = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
    posts = [
        _window_post("new", datetime(2026, 10, 10, 11, 30, tzinfo=UTC)),
        _window_post("edge", since),
        _window_post("old", datetime(2026, 10, 10, 10, 59, tzinfo=UTC)),
        _window_post("untimed", None),
    ]

    kept = _within_window(posts, since)

    assert [post["reddit_post_id"] for post in kept] == ["new", "edge", "untimed"]


async def test_rss_fetch_window_filters_and_caps(monkeypatch):
    source = RssSource("agent")
    since = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)

    async def fake_fetch(subreddit, limit):
        return [
            _window_post("a", datetime(2026, 10, 10, 11, 50, tzinfo=UTC)),
            _window_post("b", datetime(2026, 10, 10, 11, 40, tzinfo=UTC)),
            _window_post("old", datetime(2026, 10, 10, 9, 0, tzinfo=UTC)),
        ]

    monkeypatch.setattr(source, "fetch", fake_fetch)

    posts = await source.fetch_window("test", since, 1)

    assert [post["reddit_post_id"] for post in posts] == ["a"]
    await source.close()


def test_parse_rss_entry_treats_a_naive_timestamp_as_utc():
    entry = SimpleNamespace(id="t3_abc", title="x", link="y", updated="2026-07-26T10:00:00")

    assert _parse_rss_entry(entry, "test")["posted_at"] == datetime(2026, 7, 26, 10, 0, tzinfo=UTC)
