# app/runtime.py
import os


def is_test_mode(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = os.getenv("TEST_MODE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}
