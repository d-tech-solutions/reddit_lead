import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.constants import EMBEDDING_DIMENSIONS
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
# Postgres — pgvector, ARRAY and UUID rule out SQLite. Tests that need it are marked `db` and skip
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


class FakeEmbeddingProvider:
    """Test double satisfying the `EmbeddingProvider` protocol — no network, no API key, no spend.

    Vectors are derived from a hash of the input, so they are deterministic and distinct per text
    but carry no semantic meaning. Good enough to prove the worker moves data correctly; useless
    for judging match quality, which needs the real model.
    """

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on or set()
        self.closed = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        for text in texts:
            if text in self.fail_on:
                raise RuntimeError("embedding provider is down")
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        # Cycle the digest bytes out to the full column width, scaled into [0, 1).
        return [digest[index % len(digest)] / 256 for index in range(EMBEDDING_DIMENSIONS)]

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


class FakeVerifier:
    """Test double satisfying the `IntentVerifier` protocol — no network, no key, no spend.

    Returns a fixed verdict, or raises for intents listed in `fail_on`, so tests can exercise the
    matcher's success and failure paths without asserting anything about real model behaviour.
    """

    def __init__(self, matches: bool = True, fail_on: set[str] | None = None) -> None:
        self.matches = matches
        self.fail_on = fail_on or set()
        self.calls: list[tuple[str, str, str]] = []
        self.closed = False

    async def verify(self, intent_text: str, direction: str, title: str, body: str):
        from app.workers.verifier import Verdict

        self.calls.append((intent_text, direction, title))
        if intent_text in self.fail_on:
            raise RuntimeError("verifier is down")
        return Verdict(matches=self.matches, reason="fake verdict", model="fake-model")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_verifier() -> FakeVerifier:
    return FakeVerifier()
