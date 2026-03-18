# app/coaching.py
import os, httpx, json, logging
from datetime import date

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_URL = "https://api.openai.com/v1/responses"
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-5.4-mini")
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("coach")

class OpenAIRateLimited(Exception):
    pass

SYSTEM_PROMPT_CHECKIN = (
    "You are a practical goals coach. Be direct. Provide a prioritized plan, "
    "obstacles, if-then plans, and a next-30-minutes action."
)

SYSTEM_PROMPT_INTRADAY = (
    "You are a practical goals coach reviewing a midday progress update. "
    "You will receive the user's morning goals alongside their current update. "
    "Explicitly acknowledge each completed goal with encouragement. "
    "For any morning goals not mentioned in the update, assume they are still in progress "
    "and carry them forward by including them in your advice for the rest of the day. "
    "Then provide clear, prioritized advice on what to focus on for the rest of the day, "
    "taking into account any new blockers. Be direct and energizing."
)

SYSTEM_PROMPT_EOD = (
    "You are a practical goals coach reviewing an end-of-day reflection. "
    "You will receive the user's morning goals alongside their reflection. "
    "Acknowledge and celebrate completed goals and wins. "
    "For any morning goals not explicitly mentioned as completed or progressed in the reflection, "
    "treat them as incomplete and carry them forward with specific, actionable advice for tomorrow. "
    "Look for signs of procrastination or avoidance in any missed or incomplete goals—name "
    "them honestly but constructively. Provide specific, actionable insights on how to "
    "approach missed goals tomorrow. Be empathetic, direct, and encouraging."
)


async def generate_coaching(
    payload: dict,
    model: str = LLM_MODEL,
    system_prompt: str = SYSTEM_PROMPT_CHECKIN,
) -> str:
    if TEST_MODE:
        log.info("[TEST MODE] generate_coaching called with keys: %s", list(payload.keys()))
        return f"[TEST MODE] Coaching stub for: {list(payload.keys())}"

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload)},
        ],
    }

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=body)

    if r.status_code == 429:
        log.error("OpenAI 429: %s", r.text)
        raise OpenAIRateLimited(r.text)

    if r.status_code >= 400:
        log.error("OpenAI error %s: %s", r.status_code, r.text)
        r.raise_for_status()

    data = r.json()

    text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")
    return text or "I generated a plan but couldn’t extract text. (We can adjust output formatting.)"
