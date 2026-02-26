# app/coaching.py
import os, httpx, json
from datetime import date

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_URL = "https://api.openai.com/v1/responses"

async def generate_coaching(payload: dict, model: str = "gpt-4.1-mini") -> str:
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
        r.raise_for_status()
        data = r.json()

    text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")
    return text or "I generated a plan but couldn’t extract text. (We can adjust output formatting.)"