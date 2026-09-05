"""Push immutable outbox events to one operator-configured HTTP receiver."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from backend.app.correlation import valid_correlation_id
from backend.app.integrations.http import NoRedirects
from backend.app.models import OutboxRow


class HttpEventSender:
    """Receivers must atomically deduplicate the stable Idempotency-Key with their effects."""

    def __init__(self, url: str, token: str = "") -> None:
        parsed = urlsplit(url)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
            or parsed.scheme not in {"https", "http"}
            or (
                parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError(
                "Use HTTPS (HTTP only on loopback), without credentials, query, or fragment."
            )
        self.url = url
        self._token = token

    def send(self, event: OutboxRow) -> str | None:
        """Acknowledge only 2xx; do not redirect, read bodies, or expose credentials in errors."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Solar-Forge-Outbox/1",
            "Idempotency-Key": str(event["id"]),
            "X-Solar-Forge-Event-ID": str(event["id"]),
        }
        trace = event["payload"].get("details", {}).get("correlation_id")
        if isinstance(trace, str) and valid_correlation_id(trace):
            headers["X-Correlation-ID"] = trace
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            request = Request(
                self.url,
                method="POST",
                headers=headers,
                data=json.dumps(event["payload"], separators=(",", ":")).encode(),
            )
            with build_opener(NoRedirects()).open(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return None
                return f"Receiver returned HTTP {response.status}."
        except HTTPError as error:
            error.close()
            return f"Receiver returned HTTP {error.code}."
        except URLError, OSError, ValueError:
            return "Receiver connection failed or timed out."
