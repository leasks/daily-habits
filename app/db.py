# app/db.py
import os
import psycopg
from contextlib import contextmanager

from app.runtime import is_test_mode


class _MockCursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _MockConn:
    def execute(self, *_args, **_kwargs):
        return _MockCursor([])


@contextmanager
def get_conn():
    if is_test_mode():
        yield _MockConn()
        return

    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        yield conn
