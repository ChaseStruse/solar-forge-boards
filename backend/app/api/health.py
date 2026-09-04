"""Health endpoint."""

from typing import Any

from flask import Blueprint, jsonify
from sqlalchemy import text

from backend.app.database import get_engine

health_blueprint: Blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def health() -> tuple[Any, int]:
    """Report application and database readiness."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return jsonify({"status": "unhealthy", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "connected"}), 200
