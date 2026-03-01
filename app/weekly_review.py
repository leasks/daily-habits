# app/weekly_review.py
"""
Weekly review script.

Fetches the previous week's check-ins and reflections for each user,
asks the LLM to identify patterns and key insights, then stores the
result as a durable memory.  Does NOT send any Telegram messages.
"""
import asyncio, json, logging
from datetime import date, timedelta

from app.db import get_conn
from app.coaching import generate_coaching

log = logging.getLogger("weekly_review")


async def _build_summary(user_id: int) -> str:
    week_ago = date.today() - timedelta(days=7)

    with get_conn() as conn:
        checkins = conn.execute(
            """
            select checkin_date, goals, importance, constraints, blocker
            from daily_checkins
            where user_id=%s and checkin_date >= %s
            order by checkin_date
            """,
            (user_id, week_ago),
        ).fetchall()

        reflections = conn.execute(
            """
            select reflection_date, goals_progress, wins, challenges, learnings
            from daily_reflections
            where user_id=%s and reflection_date >= %s
            order by reflection_date
            """,
            (user_id, week_ago),
        ).fetchall()

    payload = {
        "task": "weekly_review",
        "period_start": str(week_ago),
        "period_end": str(date.today()),
        "checkins": [
            {
                "date": str(r[0]),
                "goals": r[1],
                "importance": r[2],
                "constraints": r[3],
                "blocker": r[4],
            }
            for r in checkins
        ],
        "reflections": [
            {
                "date": str(r[0]),
                "goals_progress": r[1],
                "wins": r[2],
                "challenges": r[3],
                "learnings": r[4],
            }
            for r in reflections
        ],
        "instructions": (
            "Analyze the week's check-ins and reflections for patterns. "
            "Identify recurring themes, consistent blockers, strengths, and areas for "
            "improvement. Extract 3–5 key insights that should be retained as durable "
            "memories for future coaching sessions."
        ),
    }

    return await generate_coaching(payload, model="gpt-4.1-mini")


async def _save_memory(user_id: int, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            insert into memories (user_id, kind, content, importance)
            values (%s, %s, %s, %s)
            """,
            (user_id, "weekly_review", content, 8),
        )


async def main() -> None:
    with get_conn() as conn:
        users = conn.execute("select id from users").fetchall()

    for (user_id,) in users:
        try:
            summary = await _build_summary(user_id)
            await _save_memory(user_id, summary)
            log.info("Weekly review saved for user %s", user_id)
        except Exception as exc:
            log.error("Weekly review failed for user %s: %s", user_id, exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
