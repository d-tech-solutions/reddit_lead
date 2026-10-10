"""Telegram's webhook: where the bot hears `/start <token>` from users connecting their chat.

Unauthenticated by design — Telegram isn't a logged-in user — so the only gate is the secret
header Telegram echoes back from `setWebhook`. Once past that gate it always answers 200, because
Telegram retries any other status and a retry storm helps nobody.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.settings import get_notifiers
from app.core.config import get_settings
from app.db.session import get_db
from app.notifiers.base import Notifier, PermanentDeliveryError, TemporaryDeliveryError
from app.notifiers.telegram import TelegramNotifier
from app.services.telegram import complete_link

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

WELCOME = "You're connected. PostPing will send your matches here."
NEED_LINK = (
    "To connect, open the link from the Notifications page in PostPing "
    "(Connect Telegram) and press Start."
)
BAD_LINK = (
    "That link has expired or was already used. Generate a new one in PostPing and try again."
)


async def _reply(notifiers: dict[str, Notifier], chat_id: int, text: str) -> None:
    notifier = notifiers.get("telegram")
    if not isinstance(notifier, TelegramNotifier):
        return
    try:
        await notifier.send_text(str(chat_id), text)
    except (TemporaryDeliveryError, PermanentDeliveryError):
        # The connection itself already succeeded or failed; a lost courtesy reply isn't a 500.
        logger.warning("telegram: could not send a reply to chat %s", chat_id)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    notifiers: dict[str, Notifier] = Depends(get_notifiers),
) -> dict[str, bool]:
    secret = get_settings().TELEGRAM_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram isn't configured"
        )
    supplied = request.headers.get(SECRET_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        update: dict[str, Any] = await request.json()
    except ValueError:
        return {"ok": True}

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    # Only one-to-one chats: connecting a group would send matches to everyone in it.
    if chat_id is None or chat.get("type") != "private" or not text.startswith("/start"):
        return {"ok": True}

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(notifiers, chat_id, NEED_LINK)
        return {"ok": True}

    if await complete_link(session, parts[1].strip(), chat_id):
        await _reply(notifiers, chat_id, WELCOME)
    else:
        await _reply(notifiers, chat_id, BAD_LINK)
    return {"ok": True}
