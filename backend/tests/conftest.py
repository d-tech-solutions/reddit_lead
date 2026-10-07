import uuid
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Database-backed test support -------------------------------------------------------------
#
# CRUD behaviour worth testing (FK cascades, the unique constraint, the tier queries) needs real
# Postgres — ARRAY and UUID columns rule out SQLite. Tests that need it are marked `db` and skip
# automatically when Postgres is unreachable, so a plain `pytest` still passes with no services
# running. See CLAUDE.md for how to run the full suite.


# Memoised per test session: probing an unreachable host costs seconds, and doing it once per
# `db` test turned a 2-second suite into a 100-second one.
_db_available: bool | None = None


# Open a connection to prove the database is actually reachable before running a `db` test.
# A skip is honest here; a connection error dressed up as a test failure is not.
async def _database_available(url: str) -> bool:
    global _db_available
    if _db_available is not None:
        return _db_available

    # Short timeout so an unreachable host fails fast rather than waiting on the OS default.
    engine = create_async_engine(url, connect_args={"timeout": 2})
    try:
        async with engine.connect():
            _db_available = True
    except Exception:  # noqa: BLE001 — any connection failure means "unavailable, skip"
        _db_available = False
    finally:
        await engine.dispose()

    return _db_available


@pytest.fixture
async def db_session() -> AsyncSession:
    """A session wrapped in a transaction that is rolled back after the test.

    Nothing a test writes survives it, so tests can run in any order against a shared database
    without cleaning up after each other.
    """
    settings = get_settings()
    if not await _database_available(settings.DATABASE_URL):
        pytest.skip(f"Postgres not reachable at {settings.DATABASE_URL.rsplit('@', 1)[-1]}")

    engine = create_async_engine(settings.DATABASE_URL)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = factory()

    try:
        yield session
    finally:
        await session.close()
        # Rolls back everything the test committed inside this outer transaction.
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def db_user(db_session: AsyncSession) -> User:
    user = User(clerk_user_id=f"user_test_{uuid.uuid4().hex[:12]}", email="t@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def db_admin_user(db_session: AsyncSession) -> User:
    user = User(
        clerk_user_id=f"user_test_{uuid.uuid4().hex[:12]}",
        email="admin@example.com",
        is_superadmin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_client(db_session: AsyncSession, db_admin_user: User) -> AsyncClient:
    """An API client authenticated as `db_admin_user` — same shape as `auth_client`."""

    async def override_db():
        yield db_session

    async def override_user():
        return db_admin_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(db_session: AsyncSession, db_user: User) -> AsyncClient:
    """An API client authenticated as `db_user`, sharing the test's rolled-back transaction.

    Both dependencies are overridden: `get_db` so the endpoint writes inside the test transaction,
    and `get_current_user` so no real Clerk token is needed. Token verification itself is covered
    separately in test_auth.py.
    """

    async def override_db():
        yield db_session

    async def override_user():
        return db_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


class FakeVerifier:
    """Test double satisfying the `IntentVerifier` protocol — no network, no key, no spend.

    Returns a fixed verdict for every candidate in the batch, or raises if any candidate's intent
    is listed in `fail_on`, so tests can exercise the matcher's success and failure paths without
    asserting anything about real model behaviour.
    """

    def __init__(self, matches: bool = True, fail_on: set[str] | None = None) -> None:
        self.matches = matches
        self.fail_on = fail_on or set()
        self.calls: list[tuple[str, str, list[tuple[uuid.UUID, str]]]] = []
        self.closed = False

    async def verify_batch(self, post_title: str, post_body: str, candidates):
        from app.workers.verifier import Verdict

        self.calls.append((post_title, post_body, list(candidates)))
        verdicts = []
        for watcher_id, intent_text in candidates:
            if intent_text in self.fail_on:
                raise RuntimeError("verifier is down")
            verdicts.append(
                Verdict(
                    watcher_id=watcher_id, matches=self.matches, reason="fake verdict",
                    model="fake-model",
                )
            )
        return verdicts

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_verifier() -> FakeVerifier:
    return FakeVerifier()


@asynccontextmanager
async def _reuse_session(session: AsyncSession):
    yield session


@pytest.fixture
def use_test_session(db_session, monkeypatch):
    """Point the notify and match workers at the test's rolled-back transaction.

    Each job opens its own session via `async_session_factory()`; this swaps that for the test's
    session so their commits stay inside the transaction.
    """
    from app.workers import match as match_worker
    from app.workers import notify

    monkeypatch.setattr(notify, "async_session_factory", lambda: _reuse_session(db_session))
    monkeypatch.setattr(match_worker, "async_session_factory", lambda: _reuse_session(db_session))
