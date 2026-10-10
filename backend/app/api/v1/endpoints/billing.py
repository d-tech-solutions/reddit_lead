"""Checkout, billing portal, and Stripe webhook handling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import (
    CheckoutRequest,
    CheckoutResponse,
    PlanRead,
    PortalResponse,
    SubscriptionRead,
)
from app.services.billing import (
    BillingError,
    create_checkout_session,
    create_portal_session,
    get_subscription,
    handle_webhook_event,
    list_plans,
    verify_webhook_signature,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanRead])
async def read_plans() -> list[PlanRead]:
    return list_plans()


@router.get("", response_model=SubscriptionRead)
async def read_billing(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubscriptionRead:
    subscription = await get_subscription(session, user.id)
    return SubscriptionRead(
        plan=user.plan,
        status=subscription.status if subscription else None,
        current_period_end=subscription.current_period_end if subscription else None,
        cancel_at_period_end=subscription.cancel_at_period_end if subscription else False,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    payload: CheckoutRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    try:
        url = await create_checkout_session(session, settings, user, payload.plan)
    except BillingError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error.message) from error
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=PortalResponse)
async def portal(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PortalResponse:
    try:
        url = await create_portal_session(session, settings, user)
    except BillingError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error.message) from error
    return PortalResponse(url=url)


# No `get_current_user` dependency: Stripe calls this directly and is authenticated by its request
# signature (verified against STRIPE_WEBHOOK_SECRET) instead of a bearer token.
@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(settings, payload, sig_header)
    except BillingError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error.message) from error

    await handle_webhook_event(session, settings, event)
    return {"received": True}
