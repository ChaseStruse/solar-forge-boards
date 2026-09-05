"""Shared application test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Engine

from backend.app import create_app
from backend.app.models import metadata, story_reference_counter


@pytest.fixture
def app(tmp_path: Path) -> Iterator[Flask]:
    """Create an isolated application backed by SQLite."""
    database_path: str = str(tmp_path / "test.db")
    application: Flask = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
            "SECRET_KEY": "test-secret",
        }
    )
    engine: Engine = application.extensions["database_engine"]
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(story_reference_counter.insert().values(id=1, value=0))
    yield application
    metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return a test client."""
    return app.test_client()


@pytest.fixture
def project_id(client: FlaskClient) -> str:
    """Create and return a project identifier."""
    response = client.post(
        "/api/v1/projects",
        json={"name": "Solar Forge", "description": "Agent platform delivery"},
    )
    payload: dict[str, dict[str, str]] = response.get_json()
    return payload["data"]["id"]


@pytest.fixture
def work_item_id(client: FlaskClient, project_id: str) -> str:
    """Create and return a work-item identifier."""
    response = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={"title": "Connect agent", "description": "Expose stable API"},
    )
    payload: dict[str, dict[str, str]] = response.get_json()
    return payload["data"]["id"]
