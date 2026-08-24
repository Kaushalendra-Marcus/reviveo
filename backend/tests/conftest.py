"""Shared pytest fixtures.

Every test gets a fresh, isolated SQLite file so tests never interfere with
each other or with a developer's real reviveo.db.
"""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # sqlite3.connect creates it fresh

    # Settings are cached via lru_cache; patch the module-level singleton's
    # database_url directly rather than fighting the cache.
    from app.config import settings
    monkeypatch.setattr(settings, "database_url", path)

    from app import db
    # Each test may run in the same thread but db._local persists a stale
    # connection from a previous test — force a fresh one.
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn
    db.init_db()

    yield db

    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def seeded_db(temp_db):
    from app.seed import ensure_seed
    ensure_seed()
    return temp_db
