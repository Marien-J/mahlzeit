"""Test setup: a real Postgres database, migrated once, one rolled-back transaction per test."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from mahlzeit.security.crypto import new_key
from mahlzeit.security.vapid import new_vapid_keys

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://mahlzeit:mahlzeit@localhost:5433/mahlzeit_test"
)
_vapid_private, _vapid_public = new_vapid_keys()
BASE_ENV = {
    "ENV": "test",
    "DATABASE_URL": TEST_DATABASE_URL,
    "BASE_URL": "http://localhost",
    "ENCRYPTION_KEY": new_key(),
    "VAPID_PRIVATE_KEY": _vapid_private,
    "VAPID_PUBLIC_KEY": _vapid_public,
    "VAPID_SUBJECT": "mailto:test@example.org",
    "SMTP_HOST": "",
    "SMTP_FROM": "",
}
os.environ.update(BASE_ENV)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from mahlzeit.config import get_settings  # noqa: E402
from mahlzeit.db import get_db  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    eng = create_engine(url)
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Override settings for one test: settings(smtp_host="x", ...)."""

    def apply(**overrides: Any) -> None:
        for key, value in overrides.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()

    get_settings.cache_clear()
    yield apply
    get_settings.cache_clear()


@pytest.fixture
def make_client(db: Session) -> Iterator[Callable[[], TestClient]]:
    """Each call returns a client with its own cookie jar, sharing the test transaction."""
    from mahlzeit.main import app

    def override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override
    clients: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(app, base_url="http://localhost")
        clients.append(client)
        return client

    yield factory
    app.dependency_overrides.clear()
    for client in clients:
        client.close()


class Clock:
    """Move time in tests: clock.set(dt), clock.advance(timedelta)."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.current = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    def set(self, at: Any) -> None:
        from mahlzeit import clock as real

        self.current = at
        real.freeze(at)

    def advance(self, delta: Any) -> None:
        self.set(self.current + delta)


@pytest.fixture
def clock() -> Iterator[Clock]:
    from mahlzeit import clock as real

    c = Clock()
    c.set(c.current)
    yield c
    real.freeze(None)
