import pytest
from fastapi import HTTPException

from app.api import deps
from app.api.deps import email_from_claims, extract_bearer_token, verify_clerk_token


class FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_extract_bearer_token_reads_the_header():
    assert extract_bearer_token(FakeRequest({"authorization": "Bearer abc.def.ghi"})) == "abc.def.ghi"


def test_extract_bearer_token_is_case_insensitive_on_the_scheme():
    assert extract_bearer_token(FakeRequest({"authorization": "bearer tok"})) == "tok"


@pytest.mark.parametrize(
    "header",
    ["", "Basic abc", "Bearer", "Bearer   ", "abc.def.ghi"],
)
def test_missing_or_malformed_header_is_401(header):
    with pytest.raises(HTTPException) as error:
        extract_bearer_token(FakeRequest({"authorization": header}))
    assert error.value.status_code == 401
    # Without this header a browser client cannot tell it should re-authenticate.
    assert error.value.headers["WWW-Authenticate"] == "Bearer"


def test_absent_header_is_401():
    with pytest.raises(HTTPException) as error:
        extract_bearer_token(FakeRequest({}))
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "a@example.com"},
        {"email_address": "a@example.com"},
        {"primary_email_address": "a@example.com"},
    ],
)
def test_email_is_read_from_any_of_the_usual_claims(claims):
    # Which claim carries the email depends on the Clerk token template, so all are checked.
    assert email_from_claims(claims) == "a@example.com"


@pytest.mark.parametrize("claims", [{}, {"email": ""}, {"email": "   "}, {"email": None}])
def test_missing_email_claim_yields_none(claims):
    assert email_from_claims(claims) is None


def test_email_is_stripped():
    assert email_from_claims({"email": "  a@example.com "}) == "a@example.com"


class FakeSettings:
    def __init__(self, secret: str = "sk_test", parties: list[str] | None = None):
        self.CLERK_SECRET_KEY = secret
        self.clerk_authorized_parties = parties or []


async def test_unconfigured_secret_key_is_a_500_not_a_401():
    # A missing server-side secret is our misconfiguration, not the caller's bad credentials.
    with pytest.raises(HTTPException) as error:
        await verify_clerk_token("tok", FakeSettings(secret=""))
    assert error.value.status_code == 500
    assert "CLERK_SECRET_KEY" in error.value.detail


async def test_verification_failure_is_401(monkeypatch):
    from clerk_backend_api.security.types import (
        TokenVerificationError,
        TokenVerificationErrorReason,
    )

    async def boom(token, options):
        raise TokenVerificationError(TokenVerificationErrorReason.TOKEN_EXPIRED)

    monkeypatch.setattr(deps, "verify_token_async", boom)

    with pytest.raises(HTTPException) as error:
        await verify_clerk_token("tok", FakeSettings())
    assert error.value.status_code == 401
    # The reason is logged, not returned — it would help someone probing the endpoint.
    assert error.value.detail == "Invalid or expired token"


async def test_verified_token_returns_its_claims(monkeypatch):
    async def ok(token, options):
        return {"sub": "user_123", "email": "a@example.com"}

    monkeypatch.setattr(deps, "verify_token_async", ok)

    claims = await verify_clerk_token("tok", FakeSettings())
    assert claims["sub"] == "user_123"


async def test_authorized_parties_are_passed_through(monkeypatch):
    captured = {}

    async def capture(token, options):
        captured["parties"] = options.authorized_parties
        captured["secret"] = options.secret_key
        return {"sub": "user_1"}

    monkeypatch.setattr(deps, "verify_token_async", capture)

    await verify_clerk_token("tok", FakeSettings(parties=["http://localhost:3000"]))

    assert captured["parties"] == ["http://localhost:3000"]
    assert captured["secret"] == "sk_test"


async def test_empty_authorized_parties_becomes_none(monkeypatch):
    # Clerk treats None as "skip the azp check"; an empty list would be a different thing.
    captured = {}

    async def capture(token, options):
        captured["parties"] = options.authorized_parties
        return {"sub": "user_1"}

    monkeypatch.setattr(deps, "verify_token_async", capture)
    await verify_clerk_token("tok", FakeSettings(parties=[]))

    assert captured["parties"] is None
