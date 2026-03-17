# app/main.py
import os, json, logging
from fastapi import BackgroundTasks, FastAPI, Request
from datetime import date
from app.db import get_conn
from app.telegram import extract_chat_id_and_text, tg_send
from app.parsing import parse_checkin, parse_reflection, parse_intraday, ParseError
from app.coaching import generate_coaching, OpenAIRateLimited, SYSTEM_PROMPT_INTRADAY, SYSTEM_PROMPT_EOD

JOB_SECRET = os.environ.get("JOB_SECRET", "")

DEFAULT_PENDING_REPLY_TYPE = "checkin"

app = FastAPI()
log = logging.getLogger("main")


def reset_pending_reply_type(user_id: int) -> None:
    """Reset a user's pending_reply_type to the default after an intraday or EOD response is handled."""
    with get_conn() as conn:
        conn.execute(
            "update users set pending_reply_type=%s where id=%s",
            (DEFAULT_PENDING_REPLY_TYPE, user_id),
        )


def upsert_user(channel: str, channel_user_id: str, from_id: str | None) -> tuple:
    """Insert or retrieve a user row.

    On first insert the telegram_from_id is recorded.  On subsequent calls the
    stored from_id is left unchanged so it can be used for sender validation.
    Returns (user_id, pending_reply_type, stored_from_id).
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            insert into users (channel, channel_user_id, telegram_from_id)
            values (%s, %s, %s)
            on conflict (channel, channel_user_id) do update
              set channel_user_id = excluded.channel_user_id
            returning id, pending_reply_type, telegram_from_id
            """,
            (channel, channel_user_id, from_id),
        ).fetchone()
        if row is None:
            return 0, DEFAULT_PENDING_REPLY_TYPE, None
        return int(row[0]), row[1] or DEFAULT_PENDING_REPLY_TYPE, row[2]


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


def _parse_jsonb_list(value, field: str, user_id: int) -> list:
    """Parse a JSONB value that is expected to be a list. Returns empty list on failure."""
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        log.warning("Malformed %s JSON for user %s", field, user_id)
    return []


def _fetch_checkin_goals(user_id: int) -> list:
    """Return today's goals from the morning check-in for the given user, or empty list."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                select goals
                from daily_checkins
                where user_id=%s and checkin_date=current_date
                limit 1
                """,
                (user_id,),
            ).fetchone()
        if row and row[0]:
            return _parse_jsonb_list(row[0], "goals", user_id)
    except Exception as exc:
        log.warning("Could not fetch today's checkin goals for user %s: %s", user_id, exc)
    return []


def _fetch_checkin_goal_updates(user_id: int) -> list:
    """Return today's goal updates (from intraday) for the given user, or empty list."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                select goal_updates
                from daily_checkins
                where user_id=%s and checkin_date=current_date
                limit 1
                """,
                (user_id,),
            ).fetchone()
        if row and row[0]:
            return _parse_jsonb_list(row[0], "goal_updates", user_id)
    except Exception as exc:
        log.warning("Could not fetch today's goal_updates for user %s: %s", user_id, exc)
    return []


async def _handle_checkin(chat_id: str, user_id: int, text: str):
    try:
        parsed = await parse_checkin(text)
    except ParseError:
        await tg_send(chat_id, "Something went wrong processing your check-in. Please try again with your top 3–5 goals, most important outcome, any constraints, and biggest blocker.")
        return

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
        coaching_text = await generate_coaching(coach_payload, model="gpt-5-mini")

        with get_conn() as conn:
            conn.execute(
                "insert into coach_outputs (checkin_id, model, coaching_text) values (%s, %s, %s)",
                (checkin_id, "gpt-5-mini", coaching_text),
            )

        await tg_send(chat_id, coaching_text)
    except OpenAIRateLimited:
        # Return 200 so Telegram doesn't resend the same update repeatedly
        await tg_send(chat_id, "I'm getting rate-limited by OpenAI right now. I'll try again in a minute—please resend if needed.")
    except Exception:
        await tg_send(chat_id, "Something went wrong generating coaching. Check logs and try again.")


async def _handle_reflection(chat_id: str, user_id: int, text: str):
    try:
        parsed = await parse_reflection(text)
    except ParseError:
        await tg_send(chat_id, "Something went wrong processing your reflection. Please try again with your goals progress, wins, challenges, and learnings.")
        return

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

    recent_summaries, memories = fetch_context(user_id)
    morning_goals = _fetch_checkin_goals(user_id)
    goal_updates = _fetch_checkin_goal_updates(user_id)

    coach_payload = {
        "today": str(date.today()),
        "morning_goals": morning_goals,
        "goal_updates": goal_updates,
        "goals_progress": parsed["goals_progress"],
        "wins": parsed["wins"],
        "challenges": parsed["challenges"],
        "learnings": parsed["learnings"],
        "recent_history": recent_summaries,
        "durable_memories": memories,
    }

    try:
        coaching_text = await generate_coaching(
            coach_payload, model="gpt-5-mini", system_prompt=SYSTEM_PROMPT_EOD
        )
        await tg_send(chat_id, coaching_text)
    except OpenAIRateLimited:
        await tg_send(chat_id, "I'm getting rate-limited by OpenAI right now. I'll try again in a minute—please resend if needed.")
    except Exception:
        await tg_send(chat_id, "Reflection saved. Great work today! \U0001f319")


async def _handle_intraday(chat_id: str, user_id: int, text: str):
    try:
        parsed = await parse_intraday(text)
    except ParseError:
        await tg_send(chat_id, "Something went wrong processing your update. Please try again with any completed goals, new blockers, and what you're focusing on next.")
        return

    morning_goals = _fetch_checkin_goals(user_id)

    if parsed["goals"]:
        with get_conn() as conn:
            conn.execute(
                """
                update daily_checkins
                set goal_updates=%s::jsonb, blocker=%s
                where user_id=%s and checkin_date=%s
                """,
                (json.dumps(parsed["goals"]), parsed["blocker"], user_id, date.today()),
            )

    recent_summaries, memories = fetch_context(user_id)

    coach_payload = {
        "today": str(date.today()),
        "morning_goals": morning_goals,
        "completed_or_updated_goals": parsed["goals"],
        "current_blocker": parsed["blocker"],
        "recent_history": recent_summaries,
        "durable_memories": memories,
    }

    try:
        coaching_text = await generate_coaching(
            coach_payload, model="gpt-5-mini", system_prompt=SYSTEM_PROMPT_INTRADAY
        )
        await tg_send(chat_id, coaching_text)
    except OpenAIRateLimited:
        await tg_send(chat_id, "I'm getting rate-limited by OpenAI right now. I'll try again in a minute—please resend if needed.")
    except Exception:
        await tg_send(chat_id, "Got it - keep going! \U0001f4aa")


async def _dispatch(chat_id: str, user_id: int, text: str, pending_type: str):
    """Route and process a Telegram message in the background."""
    try:
        if pending_type == "eod":
            try:
                await _handle_reflection(chat_id, user_id, text)
            finally:
                reset_pending_reply_type(user_id)
        elif pending_type == "intraday":
            try:
                await _handle_intraday(chat_id, user_id, text)
            finally:
                reset_pending_reply_type(user_id)
        else:
            await _handle_checkin(chat_id, user_id, text)
    except Exception:
        log.exception("Unhandled error in background dispatch for chat %s", chat_id)


@app.post("/webhooks/telegram")
async def telegram_webhook(req: Request, background_tasks: BackgroundTasks):
    update = await req.json()
    chat_id, text, from_id = extract_chat_id_and_text(update)
    if not chat_id or not text:
        return {"ok": True}

    user_id, pending_type, stored_from_id = upsert_user("telegram", chat_id, from_id)

    # Validate that the sender matches the registered user for this chat.
    # A legitimate Telegram message always carries a from.id.  If from_id is
    # absent on a message sent to an already-registered chat, or if it differs
    # from the stored value, the request is silently dropped to prevent
    # spoofing / misuse by unauthorised users.
    if stored_from_id is not None and (
        from_id is None or stored_from_id != from_id
    ):
        log.warning(
            "Sender mismatch for chat %s: expected from_id=%s got %s — ignoring",
            chat_id, stored_from_id, from_id,
        )
        return {"ok": True}

    # Schedule message processing as a background task so HTTP 200 is returned
    # to Telegram immediately.  This prevents Telegram from retrying the same
    # update when the combined LLM calls (parsing + coaching) take longer than
    # Telegram's ~60 s webhook timeout, which was causing double responses.
    background_tasks.add_task(_dispatch, chat_id, user_id, text, pending_type)
    return {"ok": True}


@app.get("/")
def root():
    return {"status": "running"}
