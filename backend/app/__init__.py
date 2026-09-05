"""Solar Forge Boards application factory."""

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template
from pydantic import ValidationError
from sqlalchemy import Engine
from werkzeug.exceptions import HTTPException

from backend.app.api.health import health_blueprint
from backend.app.api.openapi import openapi_blueprint
from backend.app.api.projects import projects_blueprint
from backend.app.api.work_items import work_items_blueprint
from backend.app.config import Settings, load_settings
from backend.app.database import create_database_engine
from backend.app.errors import AppError
from backend.app.ui.routes import ui_blueprint

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""
    settings: Settings = load_settings()
    template_folder: str = str(PROJECT_ROOT / "frontend" / "templates")
    static_folder: str = str(PROJECT_ROOT / "frontend" / "static")
    app: Flask = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config.from_mapping(
        DATABASE_URL=settings.database_url,
        SECRET_KEY=settings.secret_key,
        JSON_SORT_KEYS=False,
    )
    if test_config is not None:
        app.config.update(test_config)

    engine: Engine = create_database_engine(str(app.config["DATABASE_URL"]))
    app.extensions["database_engine"] = engine

    app.register_blueprint(health_blueprint)
    app.register_blueprint(openapi_blueprint)
    app.register_blueprint(projects_blueprint)
    app.register_blueprint(work_items_blueprint)
    app.register_blueprint(ui_blueprint)

    register_error_handlers(app)
    return app


def register_error_handlers(app: Flask) -> None:
    """Register consistent JSON and HTML error responses."""

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError) -> tuple[Any, int]:
        if error.prefers_html:
            return render_template("error.html", error=error), error.status_code
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[Any, int]:
        details: list[Any] = error.errors(
            include_url=False, include_context=False, include_input=False
        )
        return jsonify({"error": {"code": "validation_error", "details": details}}), 422

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "error": {
                        "code": error.name.lower().replace(" ", "_"),
                        "message": error.description,
                    }
                }
            ),
            error.code or 500,
        )
