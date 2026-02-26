# app/main.py
import os, json
from fastapi import FastAPI, Request
from datetime import date
from app.db import get_conn
from app.telegram import extract_chat_id_and_text, tg_send
from app.parsing import parse_checkin, parse_reflection
from app.coaching import generate_coaching
from app.coaching import OpenAIRateLimited

JOB_SECRET = os.environ.get("JOB_SECRET", "")

app = FastAPI()


def upsert_user(channel: str, channel_user_id: str) -> tuple:
    with get_conn() as conn:
        row = conn.execute(
            """
            insert into users (channel, channel_user_id)
            values (%s, %s)
            on conflict (channel, channel_user_id) do update
              set channel_user_id = excluded.channel_user_id
            returning id, pending_reply_type
            """,
            (channel, channel_user_id),
        ).fetchone()
        if row is None:
            return 0, "checkin"
        return int(row[0]), row[1] or "checkin"


def fetch_context(user_id: int):
    with get_conn() as conn:
        recent = conn.execute(
            """
            select checkin_date, goals, importance, constraints, blocker
            from daily_checkins
            where user_id=%s
            order by checkin_date desc
            limit 7
            """,
            (user_id,),
        ).fetchall()

        mem = conn.execute(
            """
            select kind, content, importance
            from memories
            where user_id=%s
            order by importance desc, created_at desc
            limit 20
            """,
            (user_id,),
        ).fetchall()

    recent_summaries = [
        {"date": str(r[0]), "goals": r[1], "importance": r[2], "constraints": r[3], "blocker": r[4]}
        for r in recent
    ]
    memories = [{"kind": m[0], "content": m[1], "importance": m[2]} for m in mem]
    return recent_summaries, memories


async def _handle_checkin(chat_id: str, user_id: int, text: str):
    parsed = parse_checkin(text)

    if not parsed["goals"]:
        await tg_send(chat_id, "I didn't catch goals. Reply with 3-5 bullet goals.")
        return

    with get_conn() as conn:
        row = conn.execute(
            """
            insert into daily_checkins (user_id, checkin_date, raw_message, goals, importance, constraints, blocker)
            values (%s, %s, %s, %s::jsonb, %s, %s, %s)
            on conflict (user_id, checkin_date) do update
              set raw_message=excluded.raw_message,
                  goals=excluded.goals,
                  importance=excluded.importance,
                  constraints=excluded.constraints,
                  blocker=excluded.blocker
            returning id
            """,
            (user_id, date.today(), text, json.dumps(parsed["goals"]),
             parsed["importance"], parsed["constraints"], parsed["blocker"]),
        ).fetchone()
        checkin_id = int(row[0]) if row else 0

    recent_summaries, memories = fetch_context(user_id)

    coach_payload = {
        "today": str(date.today()),
        "goals": parsed["goals"],
        "most_important_outcome": parsed["importance"],
        "constraints": parsed["constraints"],
        "blocker": parsed["blocker"],
        "recent_history": recent_summaries,
        "durable_memories": memories,
    }

    try:
        coaching_text = await generate_coaching(coach_payload, model="gpt-4.1-mini")

        with get_conn() as conn:
            conn.execute(
                "insert into coach_outputs (checkin_id, model, coaching_text) values (%s, %s, %s)",
                (checkin_id, "gpt-4.1-mini", coaching_text),
            )

        await tg_send(chat_id, coaching_text)
    except OpenAIRateLimited:
        # Return 200 so Telegram doesn't resend the same update repeatedly
        await tg_send(chat_id, "I'm getting rate-limited by OpenAI right now. I'll try again in a minute—please resend if needed.")
    except Exception:
        await tg_send(chat_id, "Something went wrong generating coaching. Check logs and try again.")


async def _handle_reflection(chat_id: str, user_id: int, text: str):
    parsed = parse_reflection(text)

    with get_conn() as conn:
        conn.execute(
            """
            insert into daily_reflections
                (user_id, reflection_date, raw_message, goals_progress, wins, challenges, learnings)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (user_id, reflection_date) do update
              set raw_message=excluded.raw_message,
                  goals_progress=excluded.goals_progress,
                  wins=excluded.wins,
                  challenges=excluded.challenges,
                  learnings=excluded.learnings
            """,
            (user_id, date.today(), text,
             parsed["goals_progress"], parsed["wins"],
             parsed["challenges"], parsed["learnings"]),
        )

    await tg_send(chat_id, "Reflection saved. Great work today! \U0001f319")


async def _handle_intraday(chat_id: str, user_id: int, text: str):
    parsed = parse_checkin(text)

    if parsed["goals"]:
        with get_conn() as conn:
            conn.execute(
                """
                update daily_checkins
                set goals=%s::jsonb, blocker=%s
                where user_id=%s and checkin_date=%s
                """,
                (json.dumps(parsed["goals"]), parsed["blocker"], user_id, date.today()),
            )

    await tg_send(chat_id, "Got it - keep going! \U0001f4aa")


@app.post("/webhooks/telegram")
async def telegram_webhook(req: Request):
    update = await req.json()
    chat_id, text = extract_chat_id_and_text(update)
    if not chat_id or not text:
        return {"ok": True}

    user_id, pending_type = upsert_user("telegram", chat_id)

    if pending_type == "eod":
        await _handle_reflection(chat_id, user_id, text)
    elif pending_type == "intraday":
        await _handle_intraday(chat_id, user_id, text)
    else:
        await _handle_checkin(chat_id, user_id, text)

    return {"ok": True}


@app.get("/")
def root():
    return {"status": "running"}
