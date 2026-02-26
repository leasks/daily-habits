# app/coaching.py
import os, httpx, json, logging

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_URL = "https://api.openai.com/v1/responses"

log = logging.getLogger("coach")

class OpenAIRateLimited(Exception):
    pass


async def _responses_call(input_payload: list, model: str, timeout: int = 45) -> dict:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    body = {
        "model": model,
        "input": input_payload,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=body)

    if r.status_code == 429:
        log.error("OpenAI 429: %s", r.text)
        raise OpenAIRateLimited(r.text)

    if r.status_code >= 400:
        log.error("OpenAI error %s: %s", r.status_code, r.text)
        r.raise_for_status()

    return r.json()


def _extract_output_text(data: dict) -> str:
    text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")
    return text

async def generate_coaching(payload: dict, model: str = "gpt-4.1-mini") -> str:
    data = await _responses_call(
        [
            {
                "role": "system",
                "content": "You are a practical goals coach. Be direct. Provide a prioritized plan, likely obstacles, and if-then plans.",
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )

    text = _extract_output_text(data)
    return text or "I generated a plan but couldn’t extract text. (We can adjust output formatting.)"


async def generate_weekly_memory_patterns(payload: dict, model: str = "gpt-4.1-mini") -> dict:
    data = await _responses_call(
        [
            {
                "role": "system",
                "content": (
                    "You review one user's weekly goals and coaching context to identify durable priorities and patterns. "
                    "Return strict JSON with key 'patterns' as an array of objects with fields: kind, content, importance. "
                    "Only include patterns with lasting value. importance must be an integer 7-10."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )

    text = _extract_output_text(data)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"patterns": []}
    return parsed if isinstance(parsed, dict) else {"patterns": []}


async def generate_daily_reflection(payload: dict, model: str = "gpt-4.1-mini") -> dict:
    data = await _responses_call(
        [
            {
                "role": "system",
                "content": (
                    "You are a coach creating a daily reflection summary from user goals and available progress evidence. "
                    "Return strict JSON with keys: achieved_goals (array), unachieved_goals (array), worked_well (string), "
                    "did_not_work (string), reflection_summary (string), next_day_prompt (string)."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )

    text = _extract_output_text(data)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
