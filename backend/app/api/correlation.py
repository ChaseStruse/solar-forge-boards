"""Bind API requests and responses to a service-visible trace identifier."""

from uuid import uuid4

from flask import Flask, Response, g, request

from backend.app.correlation import correlation_id, valid_correlation_id
from backend.app.errors import AppError


def register_correlation(app: Flask) -> None:
    """Install tracing before route validation, including failed requests."""

    @app.before_request
    def begin_trace() -> None:
        if not request.path.startswith("/api/v1/"):
            return
        supplied = request.headers.get("X-Correlation-ID")
        value = supplied if supplied and valid_correlation_id(supplied) else str(uuid4())
        g.correlation_token = correlation_id.set(value)
        g.correlation_id = value
        if supplied is not None and not valid_correlation_id(supplied):
            raise AppError("invalid_correlation_id", "Invalid X-Correlation-ID header.", 422)

    @app.after_request
    def finish_trace(response: Response) -> Response:
        if "correlation_id" in g:
            response.headers["X-Correlation-ID"] = g.correlation_id
        return response

    @app.teardown_request
    def clear_trace(error: BaseException | None) -> None:
        if "correlation_token" in g:
            correlation_id.reset(g.pop("correlation_token"))
