"""Additive, transactional migrations for portable SQLite databases."""
from functools import wraps
import inspect
import sqlite3
import time

from .records import DomainError

SCHEMA_VERSION = 2


def bounded_query(function):
    """Interrupt SQLite work and check Python projection loops against one deadline."""
    signature = inspect.signature(function)
    @wraps(function)
    def call(self, *args, **kwargs):
        arguments = signature.bind(self, *args, **kwargs)
        bounds = self._budget(arguments.arguments.get("budget"))
        deadline = time.monotonic() + bounds["max_request_wall_ms"] / 1000
        self._query_deadline = deadline
        self.db.execute("PRAGMA busy_timeout=" + str(bounds["max_request_wall_ms"]))
        self.db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        try:
            return function(self, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            if time.monotonic() >= deadline:
                raise DomainError("query_budget_exhausted", "Query deadline reached; interrupted work was not returned as complete") from exc
            raise
        finally:
            self.db.set_progress_handler(None, 0)
            self._query_deadline = None
            self.db.execute("PRAGMA busy_timeout=10000")
    return call


def migrate(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise DomainError("newer_database", "This database requires a newer application version")
    # Version 0 is the original reference schema; core tables are retained.
    if version < 2:
        db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS vector_indexes(
          id TEXT PRIMARY KEY, corpus TEXT NOT NULL, snapshot_id TEXT NOT NULL,
          created TEXT NOT NULL, profile TEXT NOT NULL, dimensions INTEGER NOT NULL,
          item_count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS vector_entries(
          index_id TEXT NOT NULL REFERENCES vector_indexes(id), kind TEXT NOT NULL,
          item_id TEXT NOT NULL, text_hash TEXT NOT NULL, vector TEXT NOT NULL,
          PRIMARY KEY(index_id,kind,item_id));
        CREATE TABLE IF NOT EXISTS model_cache(
          cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS model_preparations(
          job_id TEXT PRIMARY KEY REFERENCES jobs(id), metadata TEXT NOT NULL);
        PRAGMA user_version=2;
        COMMIT;
        """)
