"""Test isolation: every test runs against a fresh throwaway SQLite file.

DATABASE_URL must be set before app.config is first imported, so this
conftest sets the env var at collection time and resets tables per test.
"""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="reviveo-tests-")
os.environ["DATABASE_URL"] = os.path.join(_TMP, "test.db")
os.environ["RUN_MODE"] = "synthetic"
os.environ["SCHEDULER_ENABLED"] = "false"

import pytest  # noqa: E402

from app import db, seed  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db.reset_all()
    seed.ensure_seed()
    yield
