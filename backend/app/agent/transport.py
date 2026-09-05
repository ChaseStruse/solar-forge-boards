"""Bounded HTTP transport using only the public JSON API."""

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


@dataclass(frozen=True)
class ApiResponse:
    """Preserve the server envelope, status, and headers for model results."""

    status: int
    body: dict[str, Any]
    headers: dict[str, str]


class Transport(Protocol):
    """Injectable boundary for real HTTP or isolated contract tests."""

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None, headers: dict[str, str]
    ) -> ApiResponse: ...


class NoRedirects(HTTPRedirectHandler):
    """Never forward approved commands to another endpoint or host."""

    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class HttpTransport:
    """Call one trusted board origin; never retry writes automatically."""

    def __init__(self, base_url: str, *, timeout: float = 15) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be a complete HTTP(S) origin without credentials")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(NoRedirects())

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None, headers: dict[str, str]
    ) -> ApiResponse:
        """Return API failures unchanged and give transport failures stable local codes."""
        if not path.startswith("/api/v1/"):
            raise ValueError("Only /api/v1 paths are supported")
        request = Request(
            self.base_url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Accept": "application/json", "Content-Type": "application/json", **headers},
            method=method,
        )
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                try:
                    body = json.loads(raw) if raw else {}
                    if not isinstance(body, dict):
                        raise ValueError("Expected a JSON object")
                except ValueError, UnicodeError:
                    body = {"error": {"code": "invalid_api_response"}}
                return ApiResponse(response.status, body, response_headers)
        except URLError, OSError, TimeoutError:
            return ApiResponse(0, {"error": {"code": "transport_error"}}, {})
