# app/main.py
import os, json
from datetime import date, timedelta

from fastapi import FastAPI, Request, HTTPException

from app.db import get_conn
from app.telegram import extract_chat_id_and_text, tg_send
from app.parsing import parse_checkin
from app.coaching import (
    generate_coaching,
    generate_daily_reflection,
    generate_weekly_memory_patterns,
    OpenAIRateLimited,
)

JOB_SECRET = os.environ.get("JOB_SECRET", "")

app = FastAPI()


def require_job_secret(req: Request):
    if not JOB_SECRET:
        return
    token = req.headers.get("x-job-secret", "")
    if token != JOB_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def upsert_user(channel: str, channel_user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            insert into users (channel, channel_user_id)
            values (%s, %s)
            on conflict (channel, channel_user_id) do update
              set channel_user_id = excluded.channel_user_id
            returning id
            """,
            (channel, channel_user_id),
        ).fetchone()
        return int(row[0])


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

        reflections = conn.execute(
            """
            select reflection_date, achieved_goals, unachieved_goals, worked_well, did_not_work, reflection_summary
            from daily_reflections
            where user_id=%s
            order by reflection_date desc
            limit 3
            """,
            (user_id,),
        ).fetchall()

    recent_summaries = [
        {
            "date": str(r[0]),
            "goals": r[1],
            "importance": r[2],
            "constraints": r[3],
            "blocker": r[4],
        }
        for r in recent
    ]
    memories = [{"kind": m[0], "content": m[1], "importance": m[2]} for m in mem]
    reflection_context = [
        {
            "date": str(r[0]),
            "achieved_goals": r[1],
            "unachieved_goals": r[2],
            "worked_well": r[3],
            "did_not_work": r[4],
            "summary": r[5],
        }
        for r in reflections
    ]
    return recent_summaries, memories, reflection_context


@app.post("/webhooks/telegram")
async def telegram_webhook(req: Request):
    update = await req.json()
    chat_id, text = extract_chat_id_and_text(update)
    if not chat_id or not text:
        return {"ok": True}

    user_id = upsert_user("telegram", chat_id)
    parsed = parse_checkin(text)

    if not parsed["goals"]:
        await tg_send(chat_id, "I didn’t catch goals. Reply with 3–5 bullet goals.")
        return {"ok": True}

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
            (
                user_id,
                date.today(),
                text,
                json.dumps(parsed["goals"]),
                parsed["importance"],
                parsed["constraints"],
                parsed["blocker"],
            ),
        ).fetchone()
        checkin_id = int(row[0])

    recent_summaries, memories, reflections = fetch_context(user_id)

    coach_payload = {
        "today": str(date.today()),
        "goals": parsed["goals"],
        "most_important_outcome": parsed["importance"],
        "constraints": parsed["constraints"],
        "blocker": parsed["blocker"],
        "recent_history": recent_summaries,
        "durable_memories": memories,
        "recent_reflections": reflections,
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
        await tg_send(chat_id, "I’m getting rate-limited by OpenAI right now. I’ll try again in a minute—please resend if needed.")
    except Exception:
        await tg_send(chat_id, "Something went wrong generating coaching. Check logs and try again.")

    return {"ok": True}


@app.post("/jobs/weekly-memory-review")
async def weekly_memory_review(req: Request):
    require_job_secret(req)

    week_start = date.today() - timedelta(days=7)

    with get_conn() as conn:
        users = conn.execute("select id from users").fetchall()

    processed = 0
    for (user_id,) in users:
        with get_conn() as conn:
            goals = conn.execute(
                """
                select checkin_date, goals, importance, constraints, blocker
                from daily_checkins
                where user_id=%s and checkin_date >= %s
                order by checkin_date asc
                """,
                (user_id, week_start),
            ).fetchall()
            memories = conn.execute(
                """
                select kind, content, importance
                from memories
                where user_id=%s
                order by importance desc, created_at desc
                limit 30
                """,
                (user_id,),
            ).fetchall()

        if not goals:
            continue

        payload = {
            "window_start": str(week_start),
            "window_end": str(date.today()),
            "goal_history": [
                {
                    "date": str(g[0]),
                    "goals": g[1],
                    "importance": g[2],
                    "constraints": g[3],
                    "blocker": g[4],
                }
                for g in goals
            ],
            "existing_memories": [{"kind": m[0], "content": m[1], "importance": m[2]} for m in memories],
        }

        try:
            analysis = await generate_weekly_memory_patterns(payload, model="gpt-4.1-mini")
        except Exception:
            continue

        patterns = analysis.get("patterns", []) if isinstance(analysis, dict) else []
        with get_conn() as conn:
            for p in patterns:
                kind = str(p.get("kind", "weekly_pattern"))[:64]
                content = str(p.get("content", "")).strip()
                try:
                    importance = int(p.get("importance", 8))
                except (TypeError, ValueError):
                    importance = 8
                importance = max(7, min(10, importance))
                if not content:
                    continue
                conn.execute(
                    """
                    insert into memories (user_id, kind, content, importance)
                    values (%s, %s, %s, %s)
                    """,
                    (user_id, kind, content, importance),
                )

        processed += 1

    return {"ok": True, "processed_users": processed}


@app.post("/jobs/daily-reflection-checkin")
async def daily_reflection_checkin(req: Request):
    require_job_secret(req)

    target_day = date.today() - timedelta(days=1)

    with get_conn() as conn:
        rows = conn.execute(
            """
            select dc.id, dc.user_id, dc.goals, dc.importance, dc.constraints, dc.blocker, u.channel, u.channel_user_id
            from daily_checkins dc
            join users u on u.id = dc.user_id
            where dc.checkin_date = %s
            """,
            (target_day,),
        ).fetchall()

    processed = 0
    for row in rows:
        checkin_id, user_id, goals, importance, constraints, blocker, channel, channel_user_id = row
        payload = {
            "date": str(target_day),
            "goals": goals,
            "importance": importance,
            "constraints": constraints,
            "blocker": blocker,
        }

        try:
            reflection = await generate_daily_reflection(payload, model="gpt-4.1-mini")
        except Exception:
            continue

        achieved = reflection.get("achieved_goals", [])
        unachieved = reflection.get("unachieved_goals", [])
        worked_well = reflection.get("worked_well", "")
        did_not_work = reflection.get("did_not_work", "")
        summary = reflection.get("reflection_summary", "")
        next_day_prompt = reflection.get("next_day_prompt", "")

        with get_conn() as conn:
            conn.execute(
                """
                insert into daily_reflections
                  (user_id, checkin_id, reflection_date, achieved_goals, unachieved_goals, worked_well, did_not_work, reflection_summary, next_day_prompt)
                values (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                on conflict (user_id, reflection_date) do update
                  set checkin_id = excluded.checkin_id,
                      achieved_goals = excluded.achieved_goals,
                      unachieved_goals = excluded.unachieved_goals,
                      worked_well = excluded.worked_well,
                      did_not_work = excluded.did_not_work,
                      reflection_summary = excluded.reflection_summary,
                      next_day_prompt = excluded.next_day_prompt
                """,
                (
                    user_id,
                    checkin_id,
                    target_day,
                    json.dumps(achieved),
                    json.dumps(unachieved),
                    worked_well,
                    did_not_work,
                    summary,
                    next_day_prompt,
                ),
            )

        if channel == "telegram" and next_day_prompt:
            await tg_send(str(channel_user_id), f"Daily reflection ({target_day}):\n{summary}\n\n{next_day_prompt}")

        processed += 1

    return {"ok": True, "processed_checkins": processed}


@app.get("/")
def root():
    return {"status": "running"}
