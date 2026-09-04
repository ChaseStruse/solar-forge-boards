# Solar Forge Boards

Solar Forge Boards is a small, server-owned project management application designed to stay fast for people and predictable for software agents. This first vertical slice includes project and work-item workflows, controlled status transitions, an immutable activity stream, a clean JSON API, and a server-rendered HTMX board.

## Quick start with Docker

Requirements: Docker with Compose.

```bash
docker compose up --build
```

Open <http://localhost:8000/ui/projects>. Compose starts PostgreSQL, applies Alembic migrations, and then starts the application. Check readiness at <http://localhost:8000/health>.

Stop the application with `docker compose down`. Add `--volumes` only when you intentionally want to erase the local database.

## Local development

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), and PostgreSQL 18.

```bash
cp .env.example .env
uv sync
docker compose up -d db
DATABASE_URL=postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards uv run flask --app backend.app.wsgi:app run --debug
```

Quality checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Repository map

```text
backend/   Flask app, services, repositories, schemas, migrations, and tests
frontend/  Jinja templates, HTMX presentation, and CSS
docker/    Production image and optional entrypoint
docs/      Architecture, API, development, and Solar-Forge notes
```

The JSON API is rooted at `/api/v1`; the web client is rooted at `/ui`. Both call the same service functions. See [docs/architecture.md](docs/architecture.md) for the dependency rules and [docs/api.md](docs/api.md) for endpoint examples.

## Current scope

- Create, list, and get projects
- Create, list, get, and update work items
- Explicit lifecycle transitions with guarded state changes
- Activity events for project creation, work-item creation, content changes, and status changes
- HTMX project list and five-column board
- Database-aware health endpoint
- PostgreSQL schema managed by Alembic

Authentication, authorization, pagination, assignments, comments, and webhooks are intentionally deferred. The boundaries needed to add them without coupling clients to the UI are already present.
# solar-forge-boards
