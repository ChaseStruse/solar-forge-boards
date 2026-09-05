"""Durability, recovery, and replay behavior at the public write boundary."""

from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any
from uuid import UUID, uuid4

import pytest
from flask import Flask, redirect, request
from flask.testing import FlaskClient
from sqlalchemy import Connection, select, update
from werkzeug.serving import make_server
from werkzeug.wrappers import Response

from backend.app.integrations.outbox import HttpEventSender
from backend.app.models import OutboxRow, activity_events, outbox_events, work_items
from backend.app.repositories import outbox as repository
from backend.app.services import outbox as service


class Sender:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.events: list[OutboxRow] = []

    def send(self, event: OutboxRow) -> str | None:
        self.events.append(event)
        return self.error


def test_domain_activity_and_outbox_rollback_together(
    app: Flask,
    client: FlaskClient,
    project_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(connection: Connection, values: dict[str, Any]) -> None:
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(repository, "enqueue", fail)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        client.post(
            f"/api/v1/projects/{project_id}/work-items",
            json={"title": "Rolled back"},
            headers={"Idempotency-Key": "rollback"},
        )
    with app.extensions["database_engine"].connect() as connection:
        assert connection.execute(select(work_items)).first() is None
        assert len(connection.execute(select(activity_events)).all()) == 1
        assert len(connection.execute(select(outbox_events)).all()) == 1


def test_outbox_preserves_trace_replays_and_deleted_story(
    client: FlaskClient,
    project_id: str,
) -> None:
    path = f"/api/v1/projects/{project_id}"
    headers = {"Idempotency-Key": "create", "X-Correlation-ID": "plan-7"}
    result = client.post(path + "/work-items", json={"title": "Captured"}, headers=headers)
    client.post(path + "/work-items", json={"title": "Captured"}, headers=headers)
    story_id = result.get_json()["data"]["id"]
    client.delete(f"/api/v1/work-items/{story_id}")
    events = client.get(path + "/outbox").get_json()["data"]
    assert len(events) == 3
    created = next(event for event in events if event["event_type"] == "work_item.created")
    assert created["payload"]["work_item_id"] == story_id
    assert created["payload"]["details"]["correlation_id"] == "plan-7"
    assert created["payload"]["id"] == created["id"]
    assert created["payload"]["schema_version"] == 1
    assert "lease_token" not in created
    assert client.get(f"/api/v1/outbox/{created['id']}").get_json()["data"] == created
    assert client.get(path + "/outbox?status=delivered").get_json()["data"] == []
    assert client.get(path + "/outbox?limit=101").status_code == 422
    assert client.get(path + "/outbox?status=invalid").status_code == 422
    assert client.get(f"/api/v1/projects/{uuid4()}/outbox").status_code == 404


def test_retry_backoff_failure_recovery_and_success(
    app: Flask,
    client: FlaskClient,
    project_id: str,
) -> None:
    engine = app.extensions["database_engine"]
    sender = Sender("Receiver returned HTTP 503.")
    now = datetime.now(UTC) + timedelta(seconds=1)
    for index in range(8):
        assert service.deliver_one(engine, sender, now=now)
        if index < 7:
            assert not service.deliver_one(engine, sender, now=now)
            now += timedelta(seconds=5 * 2**index)
    event_id = sender.events[0]["id"]
    event = client.get(f"/api/v1/outbox/{event_id}").get_json()["data"]
    assert event["status"] == "failed" and event["attempts"] == 8
    assert event["last_error"] == "Receiver returned HTTP 503."
    assert len({event["id"] for event in sender.events}) == 1
    assert not service.deliver_one(engine, sender, now=now + timedelta(days=1))
    retry_url = f"/api/v1/outbox/{event_id}/retry"
    assert client.post(retry_url, json={"status": "delivered"}).status_code == 422
    retried = client.post(retry_url, json={}, headers={"Idempotency-Key": "retry"})
    assert retried.status_code == 200
    assert retried.get_json()["data"]["attempt_limit"] == 16
    assert (
        client.post(retry_url, json={}, headers={"Idempotency-Key": "retry"}).get_json()
        == retried.get_json()
    )
    assert client.post(retry_url, json={}).status_code == 409
    sender.error = None
    assert service.deliver_one(engine, sender, now=now)
    assert service.get_event(engine, event_id)["status"] == "delivered"
    assert not service.deliver_one(engine, sender, now=now + timedelta(days=1))
    assert client.post(retry_url, json={}).status_code == 409
    assert client.post(f"/api/v1/outbox/{uuid4()}/retry", json={}).status_code == 404


def test_lease_recovery_fences_old_worker(app: Flask, project_id: str) -> None:
    engine = app.extensions["database_engine"]
    now = datetime.now(UTC) + timedelta(seconds=1)
    first_token, second_token = uuid4(), uuid4()
    with engine.begin() as connection:
        first = repository.claim(connection, now, now + timedelta(seconds=60), first_token, ())
    assert first is not None
    with engine.begin() as connection:
        assert repository.claim(connection, now, now + timedelta(seconds=60), uuid4(), ()) is None
    with engine.begin() as connection:
        second = repository.claim(
            connection, now + timedelta(seconds=61), now + timedelta(seconds=121), second_token, ()
        )
        assert second is not None and second["id"] == first["id"]
        assert second["attempts"] == 2
        assert not repository.finish(connection, first["id"], first_token, {"status": "delivered"})
        assert repository.finish(connection, second["id"], second_token, {"status": "delivered"})


def test_expired_last_attempt_is_observable_and_event_filter_is_respected(
    app: Flask,
    client: FlaskClient,
    project_id: str,
) -> None:
    engine = app.extensions["database_engine"]
    sender = Sender()
    now = datetime.now(UTC) + timedelta(seconds=1)
    assert not service.deliver_one(engine, sender, event_types=("work_item.created",), now=now)
    with engine.begin() as connection:
        connection.execute(
            update(outbox_events).values(
                status="processing",
                attempts=8,
                lease_token=uuid4(),
                lease_until=now - timedelta(seconds=1),
            )
        )
    assert not service.deliver_one(engine, sender, now=now)
    failed = client.get(f"/api/v1/projects/{project_id}/outbox?status=failed").get_json()["data"]
    assert len(failed) == 1 and "lease expired" in failed[0]["last_error"]


def test_disabled_worker_sends_nothing(app: Flask, project_id: str) -> None:
    app.config["OUTBOX_URL"] = ""
    result = app.test_cli_runner().invoke(args=["deliver-outbox", "--once"])
    assert result.exit_code != 0 and "no events were sent" in result.output
    assert (
        service.list_events(app.extensions["database_engine"], UUID(project_id))[0]["attempts"] == 0
    )


def test_http_receiver_deduplicates_retry_after_lost_ack(app: Flask, project_id: str) -> None:
    """An event applied before a failed acknowledgement is retried with the identical key."""
    receiver = Flask("test-receiver")
    effects: set[str] = set()
    received: list[dict[str, Any]] = []

    @receiver.post("/events")
    def receive() -> tuple[str, int]:
        payload = request.get_json()
        assert request.headers["Idempotency-Key"] == payload["id"]
        assert request.headers["X-Solar-Forge-Event-ID"] == payload["id"]
        assert request.headers["Authorization"] == "Bearer test-only-token"
        received.append(payload)
        effects.add(payload["id"])
        return "", 503 if len(received) == 1 else 204

    server = make_server("127.0.0.1", 0, receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sender = HttpEventSender(f"http://127.0.0.1:{server.server_port}/events", "test-only-token")
        engine = app.extensions["database_engine"]
        now = datetime.now(UTC) + timedelta(seconds=1)
        assert service.deliver_one(engine, sender, now=now)
        assert service.deliver_one(engine, sender, now=now + timedelta(seconds=6))
        assert len(received) == 2 and received[0] == received[1]
        assert len(effects) == 1
        assert service.get_event(engine, UUID(received[0]["id"]))["status"] == "delivered"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/events",
        "https://user:pass@example.com/events",
        "file:///tmp/events",
        "https://example.com/events?secret=x",
    ],
)
def test_delivery_rejects_unsafe_configuration(url: str) -> None:
    with pytest.raises(ValueError):
        HttpEventSender(url)


def test_http_delivery_never_follows_redirects(app: Flask, project_id: str) -> None:
    receiver = Flask("redirect-test")
    destinations: list[str] = []

    @receiver.post("/redirect")
    def redirect_event() -> Response:
        return redirect("/unexpected", code=307)

    @receiver.post("/unexpected")
    def unexpected() -> str:
        destinations.append("unexpected")
        return ""

    server = make_server("127.0.0.1", 0, receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        engine = app.extensions["database_engine"]
        sender = HttpEventSender(f"http://127.0.0.1:{server.server_port}/redirect")
        assert service.deliver_one(engine, sender, now=datetime.now(UTC) + timedelta(seconds=1))
        assert destinations == []
        event = service.list_events(engine, UUID(project_id))[0]
        assert event["status"] == "pending" and event["last_error"] == "Receiver returned HTTP 307."
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
