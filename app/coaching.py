# app/coaching.py
import os, httpx, json, logging
from datetime import date

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_URL = "https://api.openai.com/v1/responses"
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("coach")

class OpenAIRateLimited(Exception):
    pass

async def generate_coaching(payload: dict, model: str = "gpt-4.1-mini") -> str:
    if TEST_MODE:
        log.info("[TEST MODE] generate_coaching called with keys: %s", list(payload.keys()))
        return f"[TEST MODE] Coaching stub for: {list(payload.keys())}"

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": "You are a practical goals coach. Be direct. Provide a prioritized plan, obstacles, if-then plans, and a next-30-minutes action."},
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
