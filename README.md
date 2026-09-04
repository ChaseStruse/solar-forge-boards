# Solar Forge Boards

Solar Forge Boards is a server-owned project and story board built for both people and software
agents. It combines a dark, responsive HTMX interface with a versioned JSON API, guarded workflow
transitions, project-scoped tags, and an immutable activity trail.

## Features

- Create projects and organize stories across Todo, In Progress, Blocked, Done, and Cancelled lanes.
- Open and edit a story's title, description, technical description, repository link, and tags.
- Move stories by dragging cards or by using the accessible movement buttons in the story editor.
- Delete stories with confirmation while retaining their project activity history.
- Start every project with Business, Coding, Configuration, and Spike tags, then add custom tags.
- Filter cards by one or more tags; multiple selected tags use OR matching.
- Switch between board presets or show and hide individual lanes. Saved lane visibility is local to
  the browser and project.
- Use the same backend rules through the human-facing UI or the `/api/v1` JSON API.

## Quick start with Docker

Requirements: Docker with Compose.

```bash
docker compose up --build
```

Open <http://localhost:8000/ui/projects>. Compose starts PostgreSQL 17, applies every Alembic
migration, and starts the application. Readiness is available at <http://localhost:8000/health>.

The development web container bind-mounts `backend/` and `frontend/`. Python changes restart the
Flask development server, while template, CSS, and JavaScript changes are served from the mounted
files. Rebuild after dependency or image changes. See
[Docker development](docs/development.md#docker-development) for migration changes.

Stop the stack without losing project data:

```bash
docker compose down
```

Only add `--volumes` when you intentionally want to erase the PostgreSQL volume:

```bash
docker compose down --volumes
```

## Local development

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), and PostgreSQL 17 or a compatible
PostgreSQL server.

```bash
uv sync
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards
uv run alembic upgrade head
uv run flask --app backend.app.wsgi:app run --debug --port 8000
```

Run the required quality checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Repository map

```text
backend/app/                 Flask factory, domain rules, services, repositories, and routes
backend/migrations/          Alembic environment and ordered production schema revisions
backend/tests/               API, service-boundary, health, and server-rendered UI tests
frontend/templates/          Jinja pages and HTMX board fragments
frontend/static/             Dark-theme CSS and browser-local board interactions
docker/                      Multi-stage application image and development helper files
docs/                        User, API, architecture, development, and agent-integration guides
```

## Documentation

- [Local LLM and coding-agent guide](AGENTS.md)
- [Documentation index](docs/README.md)
- [User guide](docs/user-guide.md)
- [JSON API reference](docs/api.md)
- [Architecture](docs/architecture.md)
- [Development and operations](docs/development.md)
- [Solar Forge agent integration](docs/solar-forge.md)
- [Recommended next steps](docs/roadmap.md)

## Current boundaries

Authentication, authorization, multi-tenancy, pagination, assignments, comments, tag editing or
deletion, project deletion, and webhooks are not implemented. Do not expose the current application
to untrusted networks. The service and repository boundaries are designed so these capabilities can
be added without coupling API clients to the HTML interface.
