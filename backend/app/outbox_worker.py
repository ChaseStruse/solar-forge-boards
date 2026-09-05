"""CLI dispatcher: PostgreSQL notifications for prompt wakeups, timed recovery for missed work."""

import logging
import time

import click
import psycopg
from flask import Flask
from sqlalchemy import make_url

from backend.app.database import create_database_engine
from backend.app.integrations.outbox import HttpEventSender
from backend.app.services.outbox import deliver_one

logger = logging.getLogger(__name__)


def register_outbox_command(app: Flask) -> None:
    """Register an explicit worker command; the web server never delivers events itself."""

    @app.cli.command("deliver-outbox")
    @click.option("--once", is_flag=True, help="Process at most 100 due events and exit.")
    def deliver_outbox(once: bool) -> None:
        url = str(app.config["OUTBOX_URL"])
        if not url:
            raise click.ClickException("Set OUTBOX_URL to enable delivery; no events were sent.")
        try:
            sender = HttpEventSender(url, str(app.config["OUTBOX_TOKEN"]))
        except ValueError as error:
            raise click.ClickException(str(error)) from None
        engine = create_database_engine(str(app.config["DATABASE_URL"]))
        types = tuple(
            part.strip()
            for part in str(app.config["OUTBOX_EVENT_TYPES"]).split(",")
            if part.strip()
        )
        try:
            if once:
                processed = 0
                while processed < 100 and deliver_one(engine, sender, event_types=types):
                    processed += 1
                click.echo(
                    f"Processed {processed} delivery attempts; inspect outbox status for results."
                )
                return
            if engine.dialect.name != "postgresql":
                raise click.ClickException(
                    "Continuous dispatch requires PostgreSQL; use --once for SQLite tests."
                )
            db_url = make_url(str(app.config["DATABASE_URL"])).set(drivername="postgresql")
            while True:
                try:
                    with psycopg.connect(
                        db_url.render_as_string(hide_password=False), autocommit=True
                    ) as listener:
                        listener.execute("LISTEN solar_forge_outbox")
                        while True:
                            for _ in range(100):
                                if not deliver_one(engine, sender, event_types=types):
                                    break
                            else:
                                continue
                            # LISTEN is active before checking work, avoiding a lost wake-up race.
                            # Recover missed notifications, due retries, and dead leases.
                            notifications = listener.notifies(timeout=5, stop_after=1)
                            try:
                                next(notifications, None)
                            finally:
                                notifications.close()
                except Exception:
                    logger.error("Outbox worker interrupted; reconnecting in five seconds.")
                    time.sleep(5)
        finally:
            engine.dispose()
