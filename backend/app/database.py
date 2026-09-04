"""Database engine helpers."""

from typing import Any

from flask import current_app
from sqlalchemy import Engine, create_engine, event


def enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Match PostgreSQL foreign-key behavior in local SQLite databases."""
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with healthy connection defaults."""
    connect_args: dict[str, bool] = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine: Engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
    return engine


def get_engine() -> Engine:
    """Return the current application's database engine."""
    engine: Engine = current_app.extensions["database_engine"]
    return engine
