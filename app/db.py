# app/db.py
import os
import logging
import psycopg
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "")
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")

log = logging.getLogger("db")


class _FakeCursor:
    """In-memory stub cursor returned by the fake connection in test mode."""

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeConn:
    """Minimal in-memory stub that satisfies get_conn() usage in test mode."""

    def execute(self, query, params=()):  # noqa: ARG002
        log.debug("[TEST MODE] db.execute: %s | params=%s", query.strip(), params)
        return _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@contextmanager
def get_conn():
    if TEST_MODE:
        yield _FakeConn()
        return
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn