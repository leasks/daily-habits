# app/daily_ping.py
import os, asyncio, argparse, logging
from app.db import get_conn
from app.telegram import tg_send

log = logging.getLogger("daily_ping")

MORNING_PROMPT = (
    "Morning check-in ☀️\n"
    "Reply with:\n"
    "1) Top 3–5 goals (bullets)\n"
    "2) Most important outcome:\n"
    "3) Constraints today:\n"
    "4) Biggest blocker:\n"
)

INTRADAY_PROMPT = (
    "Midday check-in 🔄\n"
    "Quick progress update:\n"
    "1) Any goals completed or updated?\n"
    "2) Any new blockers?\n"
    "3) What are you focusing on next?\n"
)

EOD_PROMPT = (
    "End of day reflection 🌙\n"
    "Reply with:\n"
    "1) Goals progress (which did you complete?):\n"
    "2) Wins today:\n"
    "3) Challenges faced:\n"
    "4) Learnings:\n"
)

PROMPTS = {
    "morning": MORNING_PROMPT,
    "intraday": INTRADAY_PROMPT,
    "eod": EOD_PROMPT,
}


async def _morning_prompt_for(chat_id: str) -> str:
    """Return morning prompt enriched with previous day reflection if available."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                select dr.goals_progress, dr.wins, dr.learnings
                from daily_reflections dr
                join users u on u.id = dr.user_id
                where u.channel = 'telegram' and u.channel_user_id = %s
                order by dr.reflection_date desc
                limit 1
                """,
                (chat_id,),
            ).fetchone()
        if row and any(row):
            return (
                MORNING_PROMPT
                + f"\n💡 Yesterday's reflection:\n"
                f"Progress: {row[0]}\nWins: {row[1]}\nLearnings: {row[2]}\n"
            )
    except Exception as exc:
        log.warning("Could not fetch previous reflection for %s: %s", chat_id, exc)
    return MORNING_PROMPT


async def main(mode: str = "morning"):
    with get_conn() as conn:
        rows = conn.execute(
            "select channel_user_id from users where channel='telegram'"
        ).fetchall()
        conn.execute(
            "update users set pending_reply_type=%s where channel='telegram'",
            (mode,),
        )

    for (chat_id,) in rows:
        if mode == "morning":
            prompt = await _morning_prompt_for(str(chat_id))
        else:
            prompt = PROMPTS[mode]
        await tg_send(str(chat_id), prompt)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Daily ping")
    parser.add_argument(
        "--mode",
        choices=["morning", "intraday", "eod"],
        default="morning",
        help="Type of prompt to send (default: morning)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.mode))
