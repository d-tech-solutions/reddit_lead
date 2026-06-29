import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """Escape special characters to prevent Telegram HTML parse errors."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_lead_notification(
    score: int,
    subreddit: str,
    intent: str,
    budget: str,
    service: str,
    summary: str,
    reply: str,
    url: str,
) -> bool:
    """Send a formatted HTML lead notification to the configured Telegram chat."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    logger.info("+++++++++++++++++++++++++++++++++++")
    logger.info(f"Token: {token[:10]}... Chat ID: {chat_id}")

    if (
        not token
        or not chat_id
        or token == "your_telegram_bot_token_here"
        or chat_id == "your_telegram_chat_id_here"
    ):
        logger.warning(
            "Telegram credentials are not fully configured. Skipping notification."
        )
        return False

    escaped_sub = escape_html(subreddit)
    escaped_intent = escape_html(intent)
    escaped_budget = escape_html(budget)
    escaped_service = escape_html(service)
    escaped_summary = escape_html(summary)
    escaped_reply = escape_html(reply)
    escaped_url = escape_html(url)

    # Format the message card with rich text HTML styling
    message_html = (
        f"🚀 <b>New Lead Found!</b> (Score: {score}/100)\n"
        f"📌 <b>Subreddit:</b> r/{escaped_sub}\n"
        f"💼 <b>Intent:</b> {escaped_intent}\n"
        f"💰 <b>Budget:</b> {escaped_budget}\n"
        f"🛠 <b>Service:</b> {escaped_service}\n\n"
        f"📝 <b>Summary:</b>\n{escaped_summary}\n\n"
        f"💬 <b>Suggested Reply (Tap to Copy):</b>\n"
        f"<code>{escaped_reply}</code>\n\n"
        f"🔗 <a href='{escaped_url}'>Open Reddit Post</a>"
    )

    telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        logger.info(
            f"Sending Telegram notification for post in r/{subreddit} (score={score})..."
        )
        response = httpx.post(telegram_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully.")
        return True
    except httpx.HTTPStatusError as http_err:
        logger.error(f"Telegram API HTTP error {http_err.response.status_code}: {http_err.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)
        return False
