# app/daily_ping.py
import argparse
import asyncio
import os

from app.db import get_conn
from app.runtime import is_test_mode
from app.telegram import tg_send

BASE_PROMPT = (
    "Morning check-in ☀️\n"
    "Reply with:\n"
    "1) Top 3–5 goals (bullets)\n"
    "2) Most important outcome:\n"
    "3) Constraints today:\n"
    "4) Biggest blocker:\n"
)


def _build_prompt_for_user(user_id: int) -> str:
    with get_conn() as conn:
        latest_reflection = conn.execute(
            """
            select reflection_date, achieved_goals, unachieved_goals, worked_well, did_not_work
            from daily_reflections
            where user_id=%s
            order by reflection_date desc
            limit 1
            """,
            (user_id,),
        ).fetchone()

    if not latest_reflection:
        return BASE_PROMPT

    reflection_date, achieved, unachieved, worked_well, did_not_work = latest_reflection
    achieved = achieved or []
    unachieved = unachieved or []

    achieved_txt = "\n".join(f"- {g}" for g in achieved) if achieved else "- (none captured)"
    unachieved_txt = "\n".join(f"- {g}" for g in unachieved) if unachieved else "- (none captured)"

    return (
        f"{BASE_PROMPT}\n"
        f"Yesterday's reflection ({reflection_date}):\n"
        f"Achieved goals:\n{achieved_txt}\n"
        f"Unachieved goals:\n{unachieved_txt}\n"
        f"What worked: {worked_well or '(not captured)'}\n"
        f"What didn't work: {did_not_work or '(not captured)'}\n\n"
        "When writing today's goals, say whether you want to rollover any unachieved goal or build on yesterday's goals. "
        "Use what worked and what didn't to improve today's plan."
    )


async def main(test_mode: bool | None = None):
    if is_test_mode(test_mode):
        return {"ok": True, "test_mode": True, "sent": 0}

    with get_conn() as conn:
        users = conn.execute("select id, channel_user_id from users where channel='telegram'").fetchall()

    sent = 0
    for user_id, chat_id in users:
        prompt = _build_prompt_for_user(int(user_id))
        await tg_send(str(chat_id), prompt)
        sent += 1

    return {"ok": True, "sent": sent}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-mode", action="store_true", help="Run without external DB/OpenAI/Telegram calls")
    args = parser.parse_args()
    if args.test_mode:
        os.environ["TEST_MODE"] = "1"
    asyncio.run(main(test_mode=args.test_mode))
