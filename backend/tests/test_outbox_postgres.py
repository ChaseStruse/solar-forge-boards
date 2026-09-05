"""Opt-in migration, locking, and notification checks on an explicitly disposable database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, make_url, select, text

from backend.app.models import outbox_events, projects
from backend.app.repositories import outbox as repository
from backend.app.schemas.projects import ProjectCreate
from backend.app.services import projects as project_service


def test_postgres_outbox_migration_locks_and_commit_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.getenv("OUTBOX_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set OUTBOX_TEST_DATABASE_URL to an empty disposable PostgreSQL database.")
    parsed = make_url(url)
    if not (parsed.database or "").startswith("solar_forge_outbox_test_"):
        pytest.fail("Refusing a database without the solar_forge_outbox_test_ prefix.")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    config = Config("alembic.ini")
    try:
        assert not inspect(engine).get_table_names(), "Integration database must start empty."
        command.upgrade(config, "923c2fb8b1fc")
        preserved_id = uuid4()
        with engine.begin() as connection:
            connection.execute(projects.insert().values(id=preserved_id, name="Preserved"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(select(outbox_events)).first() is None
            assert connection.execute(select(projects.c.name)).scalar_one() == "Preserved"
        with psycopg.connect(
            parsed.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True,
        ) as listener:
            listener.execute("LISTEN solar_forge_outbox")
            with engine.connect() as connection:
                transaction = connection.begin()
                project_service.create_project(connection, ProjectCreate(name="Rollback"))
                transaction.rollback()
            assert list(listener.notifies(timeout=0.1, stop_after=1)) == []
            project_service.create_project(engine, ProjectCreate(name="First"))
            assert len(list(listener.notifies(timeout=1, stop_after=1))) >= 1
            project_service.create_project(engine, ProjectCreate(name="Second"))
        now = datetime.now(UTC) + timedelta(seconds=1)
        with engine.connect() as first, engine.connect() as second:
            one, two = first.begin(), second.begin()
            try:
                first.execute(text("SET LOCAL lock_timeout = '2s'"))
                second.execute(text("SET LOCAL lock_timeout = '2s'"))
                claimed_one = repository.claim(first, now, now + timedelta(seconds=60), uuid4(), ())
                claimed_two = repository.claim(
                    second, now, now + timedelta(seconds=60), uuid4(), ()
                )
                assert claimed_one is not None and claimed_two is not None
                assert claimed_one["id"] != claimed_two["id"]
            finally:
                one.rollback()
                two.rollback()
        command.downgrade(config, "923c2fb8b1fc")
        assert "outbox_events" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert set(connection.execute(select(projects.c.name)).scalars()) == {
                "Preserved",
                "First",
                "Second",
            }
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(select(outbox_events)).first() is None
    finally:
        engine.dispose()
