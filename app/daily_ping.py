# app/daily_ping.py
import os, asyncio
from app.db import get_conn
from app.telegram import tg_send

PROMPT = (
    "Morning check-in ☀️\n"
    "Reply with:\n"
    "1) Top 3–5 goals (bullets)\n"
    "2) Most important outcome:\n"
    "3) Constraints today:\n"
    "4) Biggest blocker:\n"
)

async def main():
    with get_conn() as conn:
        users = conn.execute("select channel_user_id from users where channel='telegram'").fetchall()

    for (chat_id,) in users:
        await tg_send(str(chat_id), PROMPT)

if __name__ == "__main__":
    asyncio.run(main())