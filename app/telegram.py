# app/telegram.py
import os
import httpx

from app.runtime import is_test_mode

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""


async def tg_send(chat_id: str, text: str):
    if is_test_mode():
        return {"ok": True, "chat_id": chat_id, "text": text, "mocked": True}
    if not API_BASE:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required when not in TEST_MODE")

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
