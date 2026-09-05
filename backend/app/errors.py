"""Application error types shared across delivery layers."""

from typing import Any


class AppError(Exception):
    """A safe error that can be presented to API or UI clients."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        details: dict[str, Any] | None = None,
        prefers_html: bool = False,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.status_code: int = status_code
        self.details: dict[str, Any] = details or {}
        self.prefers_html: bool = prefers_html

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Serialize the error envelope."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


def not_found(resource: str, identifier: str, *, html: bool = False) -> AppError:
    """Build a standard resource-not-found error."""
    return AppError(
        "not_found",
        f"{resource} '{identifier}' was not found.",
        404,
        prefers_html=html,
    )


def version_conflict() -> AppError:
    """Build the public error used when a conditional write observes a newer revision."""
    return AppError(
        "version_conflict",
        "The resource has changed since the version supplied by the client.",
        409,
    )
