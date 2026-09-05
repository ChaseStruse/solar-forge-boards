"""Shared HTTP redirect policy for fixed-origin integrations."""

from typing import Any
from urllib.request import HTTPRedirectHandler, Request


class NoRedirects(HTTPRedirectHandler):
    """Never forward approved commands to another endpoint or host."""

    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None
