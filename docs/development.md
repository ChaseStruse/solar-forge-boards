# Development

## Local setup

Solar Forge Boards targets Python 3.14 and uses uv exclusively for environments, dependencies, and
commands. The Compose database publishes PostgreSQL 17 on local port 5432.

```bash
uv sync
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards
uv run alembic upgrade head
uv run flask --app backend.app.wsgi:app run --debug --port 8000
```

Open <http://localhost:8000/ui/projects>. Stop only the database with `docker compose stop db`, or
stop all Compose services with `docker compose down`. The named database volume survives both.

The committed `.env.example` is a reference file and `.env` is ignored. The application does not
load `.env` automatically; export variables in the shell or provide them through the process or
container environment.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL on `localhost:5432` | SQLAlchemy database URL used by Flask and Alembic |
| `FLASK_SECRET_KEY` | `development-only-secret` | Flask signing key; replace outside local development |

Compose supplies its own values and uses the database service hostname `db`. The production image
and the Compose development server both listen on port 8000.

## Docker development

For the complete application stack, run:

```bash
docker compose up --build
```

Compose bind-mounts `backend/` and `frontend/` into the web container and runs Flask's debug
reloader. Python changes restart the server; Jinja, CSS, and JavaScript changes are read from the
mounted source without an image rebuild. Re-run with `--build` after changing `pyproject.toml`,
`uv.lock`, or `docker/Dockerfile`.

The migration service is one-shot and migrations are copied into its image rather than bind-mounted.
After adding a migration while the stack is running, rebuild and rerun that service:

```bash
docker compose up --build migrate
```

Then restart `web` if it was waiting on or stopped with the migration service:

```bash
docker compose up -d web
```

Do not use `docker compose down --volumes` during ordinary development; that option permanently
removes the local PostgreSQL volume.

## Schema changes

Change the SQLAlchemy Core metadata first, then generate and inspect a migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Never rely on `metadata.create_all` in production. It is used only to keep isolated unit tests fast.

Commit the model change and its Alembic revision together. Verify both `upgrade()` and `downgrade()`
logic, and consider how the migration handles existing project and story data. The tag migration is
an example of backfilling defaults for existing projects without deleting them.

## Required checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Tests run against a temporary SQLite database for fast service and delivery-layer feedback. Run a
Compose smoke test when changing migrations, PostgreSQL constraints, container startup, or database
configuration because SQLite cannot validate those deployment details.

## Implementation conventions

- Put all imports at module scope.
- Type every function parameter and return value and all important intermediate values.
- Prefer small functions and immutable Pydantic commands.
- Place business validation in services, request-shape validation in schemas, and database operations in repositories.
- Let a service own the full transaction for a use case.
- Add an activity event for changes a human or agent would reasonably ask about later.
- Add JSON API behavior first; HTMX routes should call the same use case.
- Keep browser JavaScript limited to local presentation state and interaction; persist domain state
  through server endpoints.
- Update the relevant file in `docs/` whenever routes, validation, transitions, configuration, or UI
  workflows change.

## Production image

`docker/Dockerfile` performs a locked, production-only `uv sync` in a build stage and copies the
environment into a slim runtime image. The runtime uses a non-root `solarboards` account and starts
Gunicorn with two workers and four threads per worker on port 8000. Compose overrides that command
with Flask's development server.

The image does not run migrations in its default command. A deployment must run
`alembic upgrade head` from the built image as a release step before accepting traffic. Supply a
production PostgreSQL `DATABASE_URL`, a strong `FLASK_SECRET_KEY`, TLS termination, and network access
controls. Authentication and authorization are not implemented, so the current application is not
safe for public exposure.

## Frontend dependencies

The base template loads DM Sans and Space Grotesk from Google Fonts and HTMX 2.0.8 from unpkg. No
Node build is required. Browser access to those CDNs is currently required for the intended fonts
and HTMX behavior. Consider vendoring these pinned assets before an offline or production deployment.

## Reference counter migration

Migration `20260905_0009` adds and seeds a durable story reference counter from existing rows.
Apply it before running the updated application; existing story numbers and project data stay intact.
References deleted before this migration cannot be recovered from the old activity payloads, so the
non-reuse guarantee starts with the seeded counter. Downgrading removes counter history; it is an
operational rollback, not a way to preserve reference allocation across subsequent upgrades.

SQLite tests explicitly seed the same singleton after creating metadata and use modern transaction
control so reservation savepoints roll back together with domain writes, matching PostgreSQL.
