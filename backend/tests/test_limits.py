import pytest

from app.core.constants import TIER_LIMITS, limits_for_plan
from app.services.limits import LimitExceeded, Usage, check_limits


def test_every_tier_in_the_prd_is_present():
    assert set(TIER_LIMITS) == {"free", "standard", "premium", "enterprise"}


@pytest.mark.parametrize(
    ("plan", "watchers", "subreddits"),
    [("free", 1, 3), ("standard", 3, 10), ("premium", 10, 50)],
)
def test_tier_numbers_match_the_prd(plan, watchers, subreddits):
    limit = limits_for_plan(plan)
    assert limit.max_watchers == watchers
    assert limit.max_subreddits == subreddits


def test_enterprise_is_unbounded():
    limit = limits_for_plan("enterprise")
    assert limit.max_watchers is None
    assert limit.max_subreddits is None


def test_unknown_plan_falls_back_to_free():
    # Failing closed matters: a typo'd plan string must not silently grant unlimited watchers.
    assert limits_for_plan("platinum") == TIER_LIMITS["free"]
    assert limits_for_plan("") == TIER_LIMITS["free"]


def test_first_watcher_is_allowed_on_free():
    check_limits("free", Usage(watchers=0, subreddits=0), new_subreddit_count=3, adding_watcher=True)


def test_second_watcher_is_refused_on_free():
    with pytest.raises(LimitExceeded, match="1 watcher"):
        check_limits(
            "free", Usage(watchers=1, subreddits=1), new_subreddit_count=1, adding_watcher=True
        )


def test_subreddit_pool_is_shared_across_watchers():
    # PRD §6: the pool is a total across watchers, not a per-watcher allowance.
    with pytest.raises(LimitExceeded, match="10 subreddits"):
        check_limits(
            "standard", Usage(watchers=2, subreddits=8), new_subreddit_count=3, adding_watcher=True
        )


def test_subreddit_pool_allows_exactly_the_limit():
    check_limits(
        "standard", Usage(watchers=2, subreddits=7), new_subreddit_count=3, adding_watcher=True
    )


def test_edit_does_not_count_a_new_watcher():
    # A user at their watcher cap must still be able to edit the watchers they have.
    check_limits(
        "free", Usage(watchers=0, subreddits=0), new_subreddit_count=3, adding_watcher=False
    )


def test_edit_still_respects_the_subreddit_pool():
    with pytest.raises(LimitExceeded, match="3 subreddits"):
        check_limits(
            "free", Usage(watchers=0, subreddits=0), new_subreddit_count=4, adding_watcher=False
        )


def test_enterprise_bypasses_both_limits():
    check_limits(
        "enterprise",
        Usage(watchers=999, subreddits=9999),
        new_subreddit_count=500,
        adding_watcher=True,
    )


def test_limit_message_names_the_limit_and_current_usage():
    # "Limit exceeded" alone makes the user go and count their own watchers.
    with pytest.raises(LimitExceeded) as error:
        check_limits(
            "standard", Usage(watchers=1, subreddits=9), new_subreddit_count=4, adding_watcher=True
        )

    message = error.value.message
    assert "10 subreddits" in message
    assert "9 already in use" in message
    assert "4 requested" in message


def test_watcher_message_is_singular_for_the_free_tier():
    with pytest.raises(LimitExceeded) as error:
        check_limits(
            "free", Usage(watchers=1, subreddits=0), new_subreddit_count=1, adding_watcher=True
        )
    assert "1 watcher;" in error.value.message
