"""Shared FastAPI dependencies — currently just turning a Clerk session token into a `User` row.

Clerk owns authentication; this module owns the join between a Clerk identity and the app's own
account row. Verification is done with Clerk's `verify_token_async`, which validates the RS256
signature against Clerk's JWKS and enforces expiry, so no request ever reaches an endpoint with an
unverified token.
"""

from __future__ import annotations

import logging

from clerk_backend_api.security import VerifyTokenOptions, verify_token_async
from clerk_backend_api.security.types import TokenVerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import DEFAULT_PLAN
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)


# Pull the bearer token out of the Authorization header.
# Returns 401 rather than 403 for anything malformed — the caller has not proven who they are.
def extract_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


# Verify a Clerk session token and return its claims.
# Raises 401 on any verification failure; the reason is logged rather than returned, since telling
# a caller *why* their token failed is a gift to anyone probing the endpoint.
async def verify_clerk_token(token: str, settings: Settings) -> dict:
    if not settings.CLERK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "CLERK_SECRET_KEY is not configured. Set it in backend/.env for local runs, "
                "or in the root .env for docker compose."
            ),
        )

    try:
        return await verify_token_async(
            token,
            VerifyTokenOptions(
                secret_key=settings.CLERK_SECRET_KEY,
                authorized_parties=settings.clerk_authorized_parties or None,
            ),
        )
    except TokenVerificationError as error:
        logger.info("auth: token verification failed (%s)", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


# Read the email out of Clerk's session claims. Which claim carries it depends on how the token
# template is configured, so check the usual spellings rather than assuming one.
def email_from_claims(claims: dict) -> str | None:
    for key in ("email", "email_address", "primary_email_address"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# Find the account for this Clerk id, creating it on first sight.
#
# Two requests from a brand-new user can race here, so a unique-violation on insert is treated as
# "someone else just created it" and re-read, rather than surfacing as a 500.
async def get_or_create_user(
    session: AsyncSession, clerk_user_id: str, email: str | None
) -> User:
    result = await session.execute(
        select(User).where(User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        # Keep the email fresh — without a Clerk webhook this is the only time we learn it changed.
        if email and user.email != email:
            user.email = email
            await session.commit()
        return user

    user = User(clerk_user_id=clerk_user_id, email=email, plan=DEFAULT_PLAN)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        user = result.scalar_one()
    else:
        logger.info("auth: created account for clerk user %s", clerk_user_id)

    return user


# The dependency endpoints actually use: a verified, persisted `User` for the calling request.
async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    claims = await verify_clerk_token(extract_bearer_token(request), settings)

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        # A token that verified but carries no subject is not usable as an identity.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing a subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_or_create_user(session, clerk_user_id, email_from_claims(claims))
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    return user


# Gate for the /admin API — everything a normal user can do, plus this.
async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
