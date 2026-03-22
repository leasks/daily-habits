# app/telegram.py
import os
import logging
import httpx
from .formatting import markdown_to_html

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("telegram")


MAX_MSG_LEN = 4096


def _split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """Split *text* into chunks of at most *max_len* characters.

    Prefers splitting at paragraph breaks (blank lines) then at single
    newlines so that HTML tags are less likely to be severed mid-tag.
    """
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while len(text) > max_len:
        pos = text.rfind("\n\n", 0, max_len)
        if pos == -1:
            pos = text.rfind("\n", 0, max_len)
        if pos == -1:
            pos = max_len
        chunks.append(text[:pos].rstrip("\n"))
        text = text[pos:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def tg_send(chat_id: str, text: str):
    if TEST_MODE:
        log.info("[TEST MODE] tg_send to %s: %s", chat_id, text)
        return
    if not text:
        return
    html_text = markdown_to_html(text)
    chunks = _split_message(html_text)
    async with httpx.AsyncClient(timeout=20) as client:
        for chunk in chunks:
            r = await client.post(
                f"{API_BASE}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
            )
            r.raise_for_status()

def extract_chat_id_and_text(update: dict):
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    sender = msg.get("from") or {}
    chat_id = chat.get("id")
    from_id = sender.get("id")
    text = msg.get("text")
    if chat_id is None or not text:
        return None, None, None
    return str(chat_id), text, str(from_id) if from_id is not None else None