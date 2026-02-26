# app/telegram.py
import os
import logging
import httpx

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("telegram")


async def tg_send(chat_id: str, text: str):
    if TEST_MODE:
        log.info("[TEST MODE] tg_send to %s: %s", chat_id, text)
        return
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_BASE}/sendMessage", json={"chat_id": chat_id, "text": text})
        r.raise_for_status()

def extract_chat_id_and_text(update: dict):
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = msg.get("text")
    if chat_id is None or not text:
        return None, None
    return str(chat_id), text