"""Request tracing independent of Flask and database transaction ownership."""

import re
from contextvars import ContextVar

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def valid_correlation_id(value: str) -> bool:
    """Accept bounded, printable identifiers safe for HTTP headers and audit payloads."""
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None
