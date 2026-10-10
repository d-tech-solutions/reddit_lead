"""Point Telegram's bot at this deployment's webhook endpoint (run once per public URL).

Telegram needs a public HTTPS address to deliver to, so locally this means a tunnel (ngrok,
cloudflared, ...) in front of the API. Re-run it whenever that address changes. Uses
TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from the environment.

    docker compose exec api python -m scripts.set_telegram_webhook https://abc123.ngrok.app
    docker compose exec api python -m scripts.set_telegram_webhook --info
    docker compose exec api python -m scripts.set_telegram_webhook --delete
"""

from __future__ import annotations

import argparse
import sys

import httpx

from app.core.config import get_settings

WEBHOOK_PATH = "/api/v1/telegram/webhook"


def call(token: str, method: str, **payload: object) -> dict:
    response = httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=15)
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("public_url", nargs="?", help="public base URL of the API, no trailing path")
    parser.add_argument("--info", action="store_true", help="show the current webhook status")
    parser.add_argument("--delete", action="store_true", help="remove the webhook")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    if args.info:
        print(call(settings.TELEGRAM_BOT_TOKEN, "getWebhookInfo"))
        return 0
    if args.delete:
        print(call(settings.TELEGRAM_BOT_TOKEN, "deleteWebhook"))
        return 0

    if not args.public_url:
        parser.error("give the public base URL, or use --info / --delete")
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        print("TELEGRAM_WEBHOOK_SECRET is not set", file=sys.stderr)
        return 1
    if not args.public_url.startswith("https://"):
        print("Telegram only delivers to https:// URLs", file=sys.stderr)
        return 1

    url = args.public_url.rstrip("/") + WEBHOOK_PATH
    result = call(
        settings.TELEGRAM_BOT_TOKEN,
        "setWebhook",
        url=url,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
        # We only act on private-chat messages; skip everything else Telegram could send.
        allowed_updates=["message"],
    )
    print(f"{url} -> {result}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
