# app/parsing.py
import os, json, logging, httpx

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_URL = "https://api.openai.com/v1/responses"
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-5.4-mini")
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("parsing")


class ParseError(Exception):
    """Raised when the LLM response cannot be parsed into structured JSON."""

_CHECKIN_SCHEMA = """{
  "goals": ["<goal 1>", "<goal 2>", "<...up to 5 goals>"],
  "importance": "<most important single outcome, or null>",
  "constraints": "<constraints the person has today, or null>",
  "blocker": "<biggest blocker mentioned, or null>"
}"""

_REFLECTION_SCHEMA = """{
  "goals_progress": "<summary of which goals were completed or progressed, or null>",
  "wins": "<wins today, or null>",
  "challenges": "<challenges faced, or null>",
  "learnings": "<learnings or takeaways, or null>"
}"""

_INTRADAY_SCHEMA = """{
  "goals": ["<updated or completed goal 1>", "..."],
  "blocker": "<new or updated blocker, or null>"
}"""

_CLASSIFICATION_SCHEMA = """{
  "type": "<goals_response or leadership_question>"
}"""


async def _call_llm(system_prompt: str, user_text: str) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    body = {
        "model": LLM_MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=body)
    r.raise_for_status()
    data = r.json()
    text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")
    return text


async def parse_checkin(text: str) -> dict:
    """Parse a morning check-in reply using an LLM."""
    if TEST_MODE:
        log.info("[TEST MODE] parse_checkin stub")
        return {"goals": ["stub goal"], "importance": None, "constraints": None, "blocker": None}

    system_prompt = (
        "You are a data-extraction assistant. Extract the user's morning check-in details "
        "from their free-form reply and return ONLY a JSON object matching this schema:\n"
        + _CHECKIN_SCHEMA
        + "\nDo not include markdown fences or any text outside the JSON object."
    )
    raw = await _call_llm(system_prompt, text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON for parse_checkin: %r", raw)
        raise ParseError("parse_checkin")
    goals = parsed.get("goals") or []
    if not isinstance(goals, list):
        goals = [goals] if goals else []
    return {
        "goals": [str(g) for g in goals[:5]],
        "importance": parsed.get("importance") or None,
        "constraints": parsed.get("constraints") or None,
        "blocker": parsed.get("blocker") or None,
    }


async def parse_reflection(text: str) -> dict:
    """Parse an end-of-day reflection reply using an LLM."""
    if TEST_MODE:
        log.info("[TEST MODE] parse_reflection stub")
        return {"goals_progress": None, "wins": None, "challenges": None, "learnings": None}

    system_prompt = (
        "You are a data-extraction assistant. Extract the user's end-of-day reflection details "
        "from their free-form reply and return ONLY a JSON object matching this schema:\n"
        + _REFLECTION_SCHEMA
        + "\nDo not include markdown fences or any text outside the JSON object."
    )
    raw = await _call_llm(system_prompt, text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON for parse_reflection: %r", raw)
        raise ParseError("parse_reflection")
    return {
        "goals_progress": parsed.get("goals_progress") or None,
        "wins": parsed.get("wins") or None,
        "challenges": parsed.get("challenges") or None,
        "learnings": parsed.get("learnings") or None,
    }


async def parse_intraday(text: str) -> dict:
    """Parse an intraday update reply using an LLM."""
    if TEST_MODE:
        log.info("[TEST MODE] parse_intraday stub")
        return {"goals": [], "blocker": None}

    system_prompt = (
        "You are a data-extraction assistant. Extract the user's midday progress update "
        "from their free-form reply and return ONLY a JSON object matching this schema:\n"
        + _INTRADAY_SCHEMA
        + "\nDo not include markdown fences or any text outside the JSON object."
    )
    raw = await _call_llm(system_prompt, text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON for parse_intraday: %r", raw)
        raise ParseError("parse_intraday")
    goals = parsed.get("goals") or []
    if not isinstance(goals, list):
        goals = [goals] if goals else []
    return {
        "goals": [str(g) for g in goals[:5]],
        "blocker": parsed.get("blocker") or None,
    }


async def classify_message(text: str) -> str:
    """Classify a user message as 'goals_response' or 'leadership_question'.

    Returns 'goals_response' by default when the classification is ambiguous or
    the LLM call fails, so that unrecognised messages fall through to the
    existing goals-coaching pipeline.
    """
    if TEST_MODE:
        log.info("[TEST MODE] classify_message stub")
        return "goals_response"

    system_prompt = (
        "You are a message classifier. Determine whether the user's message is:\n"
        "- 'goals_response': A reply related to daily goal progress -- listing tasks, "
        "goals, blockers, wins, progress updates, or reflections on their work day.\n"
        "- 'leadership_question': A question or request about leadership "
        "development, management, team dynamics, organisational skills, or personal "
        "effectiveness as a leader.\n\n"
        "Return ONLY a JSON object matching this schema:\n"
        + _CLASSIFICATION_SCHEMA
        + "\nDo not include markdown fences or any text outside the JSON object."
    )
    raw = await _call_llm(system_prompt, text)
    try:
        parsed = json.loads(raw)
        msg_type = parsed.get("type", "goals_response")
        if msg_type not in ("goals_response", "leadership_question"):
            return "goals_response"
        return msg_type
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON for classify_message: %r", raw)
        return "goals_response"
