"""Insert fake confirmed matches so the feed UI can be exercised without a live pipeline.

**Development only.** A real match needs the whole chain — ingestion, an `OPENAI_API_KEY` for the
embedding worker, and an `ANTHROPIC_API_KEY` for the verifier. This script skips all of it and
writes the end state directly, so the feed can be built and checked before those keys exist.

The rows it writes are indistinguishable from real ones, which is the point and also the risk:
run it against a database you do not mind polluting. `--clear` removes only what it wrote,
identified by the `seed_` prefix on `reddit_post_id`.

    docker compose exec api python -m scripts.seed_matches --email you@example.com
    docker compose exec api python -m scripts.seed_matches --clear
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.user import User
from app.models.watcher import Watcher

# Everything this script writes carries this prefix, so `--clear` can find its own rows and only
# its own rows.
SEED_PREFIX = "seed_"

# Plausible r/forhire posts. Written to read like the real thing — a feed full of "test post 1"
# tells you the plumbing works but nothing about whether the UI is usable.
SAMPLE_POSTS = [
    (
        "[Hiring] Need a React dev to finish a half-built dashboard",
        (
            "We have a Next.js admin dashboard that's about 60% done. The previous contractor "
            "went quiet. Looking for someone to pick it up, finish the remaining views and clean "
            "up the state management. Budget is flexible for the right person."
        ),
        (
            "They are asking to hire a developer for React work, which is exactly what this "
            "watcher is looking for."
        ),
    ),
    (
        "[Hiring] Python developer for a small scraping + reporting job",
        (
            "Need a script that pulls data from a few public sources daily and emails a summary. "
            "Should take an experienced person a couple of days. Paid hourly or fixed, your call."
        ),
        "A direct request to hire a Python developer for a defined piece of work.",
    ),
    (
        "[Hiring] Looking for a frontend contractor, 10-15 hrs/week ongoing",
        (
            "Small SaaS company, we need ongoing frontend help. Mostly React and Tailwind, "
            "occasional design work. Long-term if it goes well."
        ),
        (
            "The poster is hiring a frontend developer on an ongoing basis — a match for someone "
            "looking for React contract work."
        ),
    ),
]


# Find the user to attach seeded matches to: the named email, or the only user if there is one.
#
# Refuses to guess when several users exist — seeding into the wrong account is confusing and
# `--clear` would not obviously undo it.
async def resolve_user(session, email: str | None) -> User:
    if email:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user with email {email!r}. Sign in once to create the account.")
        return user

    users = list((await session.execute(select(User))).scalars())
    if not users:
        raise SystemExit("No users yet. Sign in through the frontend once, then re-run.")
    if len(users) > 1:
        addresses = ", ".join(u.email or str(u.id) for u in users)
        raise SystemExit(f"Several users exist — pass --email. Found: {addresses}")
    return users[0]


# Use the user's existing watcher, or create one so the script works on a fresh account.
async def resolve_watcher(session, user: User) -> Watcher:
    result = await session.execute(
        select(Watcher).where(Watcher.user_id == user.id).order_by(Watcher.created_at)
    )
    watcher = result.scalars().first()
    if watcher is not None:
        return watcher

    watcher = Watcher(
        user_id=user.id,
        name="Seeded watcher",
        intent_text="someone looking to hire a React or Python developer for contract work",
        subreddits=["forhire"],
        direction="requesting",
    )
    session.add(watcher)
    await session.flush()
    return watcher


# Write one post + one confirmed match per sample, spaced an hour apart so the feed has an order.
async def seed(session, watcher: Watcher) -> int:
    now = datetime.now(UTC)
    written = 0

    for index, (title, body, reason) in enumerate(SAMPLE_POSTS):
        suffix = uuid.uuid4().hex[:8]
        posted = now - timedelta(hours=index + 1)

        post = RedditPost(
            reddit_post_id=f"{SEED_PREFIX}{suffix}",
            subreddit=watcher.subreddits[0] if watcher.subreddits else "forhire",
            title=title,
            body=body,
            author=f"seed_user_{index}",
            permalink=f"https://www.reddit.com/r/forhire/comments/{suffix}/",
            posted_at=posted,
        )
        session.add(post)
        await session.flush()

        session.add(
            Match(
                watcher_id=watcher.id,
                reddit_post_id=post.id,
                # Real-looking numbers from the direction experiment: a confirmed request sits
                # around 0.55-0.65 similarity with a negative direction score.
                similarity=0.62 - index * 0.02,
                direction_score=-0.05 - index * 0.01,
                adjusted_score=0.57 - index * 0.02,
                llm_verified=True,
                llm_reason=reason,
                llm_model="seed-script",
                created_at=posted,
                verified_at=posted,
            )
        )
        written += 1

    await session.commit()
    return written


# Delete every row this script has ever written, matched on the reddit_post_id prefix.
# The matches go with them via matches_reddit_post_id_fkey ON DELETE CASCADE.
async def clear(session) -> int:
    result = await session.execute(
        delete(RedditPost).where(RedditPost.reddit_post_id.startswith(SEED_PREFIX))
    )
    await session.commit()
    return int(result.rowcount or 0)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Which user to seed matches for")
    parser.add_argument("--clear", action="store_true", help="Delete seeded rows and exit")
    args = parser.parse_args()

    settings = get_settings()
    if settings.ENVIRONMENT not in ("local", "development", "test"):
        raise SystemExit(f"Refusing to seed fake data in ENVIRONMENT={settings.ENVIRONMENT!r}")

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            if args.clear:
                removed = await clear(session)
                print(f"Removed {removed} seeded posts (and their matches).")
                return

            user = await resolve_user(session, args.email)
            watcher = await resolve_watcher(session, user)
            written = await seed(session, watcher)
            print(f"Seeded {written} matches for {user.email or user.id} on '{watcher.name}'.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # No SystemExit handler here: Python already prints its message to stderr and sets the exit
    # code. Catching it to print again just says everything twice.
    asyncio.run(main())
