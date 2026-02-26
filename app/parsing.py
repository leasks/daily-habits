# app/parsing.py
import re

def parse_checkin(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    goals = []
    importance = None
    constraints = None
    blocker = None

    for l in lines:
        if re.match(r"^(\-|\•|\d+\)|\d+\.)\s+", l):
            goals.append(re.sub(r"^(\-|\•|\d+\)|\d+\.)\s+", "", l).strip())
        elif l.lower().startswith("most important"):
            importance = l.split(":", 1)[-1].strip() if ":" in l else l
        elif l.lower().startswith("constraints"):
            constraints = l.split(":", 1)[-1].strip() if ":" in l else l
        elif l.lower().startswith("blocker"):
            blocker = l.split(":", 1)[-1].strip() if ":" in l else l

    if not goals:
        chunks = [c.strip() for c in re.split(r"[;\n]", text) if c.strip()]
        goals = chunks[:5]

    return {"goals": goals[:5], "importance": importance, "constraints": constraints, "blocker": blocker}