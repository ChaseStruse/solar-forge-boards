# Solar Forge Boards agent guide

This file is the operating brief for local LLMs and coding agents editing this repository. Read it
before making changes, then consult the linked documentation for the part of the system in scope.

## Project intent

Solar Forge Boards is a project and story board for both people and software agents. The backend is
the source of truth. The server-rendered HTMX interface and the JSON API are clients of the same
service functions and must enforce identical business behavior.

In the UI, records are called **stories**. Backend code and API paths currently call them
**work items**. These terms refer to the same resource.

## Read before editing

- `README.md`: setup, feature summary, and repository boundaries.
- `docs/architecture.md`: dependency direction, data model, transactions, and browser-local state.
- `docs/api.md`: complete public API, validation limits, errors, and lifecycle policy.
- `docs/user-guide.md`: expected human-facing behavior.
- `docs/development.md`: local and Docker workflows, migrations, checks, and deployment notes.
- `docs/solar-forge.md`: guidance for agent-facing integrations.

If behavior changes, update the relevant documentation in the same change.

## Technology and commands

- Python 3.14
- Flask application factory and blueprints
- Pydantic request/response schemas
- SQLAlchemy Core, not the SQLAlchemy ORM
- PostgreSQL 17 in Compose; SQLite only for isolated tests
- Alembic migrations
- Jinja, HTMX, plain JavaScript, and CSS; there is no Node build
- uv for environments, dependencies, locking, and commands

Never use `pip`. Add or remove dependencies with `uv add` or `uv remove`, and commit both
`pyproject.toml` and `uv.lock`.

Common commands:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
docker compose config -q
```

Run the local application with:

```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards
uv run alembic upgrade head
uv run flask --app backend.app.wsgi:app run --debug --port 8000
```

Or run the hot-reloading stack with `docker compose up --build`.

## Repository map

```text
backend/app/api/             Versioned JSON routes and response envelopes
backend/app/ui/              HTML form routes and Jinja/HTMX rendering
backend/app/schemas/         Pydantic request and response contracts
backend/app/services/        Use cases, validation, transactions, and activity events
backend/app/repositories/    SQLAlchemy Core statements with no commits or domain validation
backend/app/domain.py        Work-item status enum and transition policy
backend/app/models.py        SQLAlchemy Core metadata and typed row shapes
backend/migrations/          Alembic environment and ordered schema history
backend/tests/               API, UI, health, and behavior tests
frontend/templates/          Pages and the replaceable board fragment
frontend/static/css/app.css  Dark cyberpunk visual system and responsive layout
frontend/static/js/board.js  Drag/drop, tag filters, and browser-local view state
```

## Architecture rules

Follow this dependency direction:

```text
API or UI route -> service -> repository -> database
                         -> domain policy
```

- Routes parse transport input and format output. They may call services, not repositories.
- Services own business rules and transaction boundaries.
- A meaningful write and its activity event belong in the same transaction.
- Repositories accept an active SQLAlchemy `Connection`; they do not validate, commit, or open
  transactions.
- Schemas reject unknown fields and define transport-level validation.
- Templates receive presentation-ready data and must not become the authoritative source of rules.
- Browser JavaScript may own presentation-only state. Persistent domain changes must call the
  backend.
- New external clients must use `/api/v1`, never scrape or call internal HTMX routes.

Prefer small typed functions and keep imports at module scope. Match the strict Ruff and mypy
configuration in `pyproject.toml`.

## Domain invariants

- Project names are unique.
- New projects atomically receive Business, Coding, Configuration, and Spike tags.
- Tags belong to exactly one project. Never permit cross-project story assignments.
- Tag names are case-insensitively unique within a project.
- New stories begin in `todo`.
- `PATCH /api/v1/work-items/{id}` must never accept `status`; use the transition endpoint.
- Multiple tag filters use OR semantics.
- Work-item API responses embed their complete tag objects.
- Story deletion is permanent, but activity remains attached to the project with a null story
  reference and a final `work_item.deleted` event.
- Activity listing returns the newest 50 events and currently has no pagination.

Allowed story transitions:

| Current status | Allowed targets |
| --- | --- |
| `todo` | `in_progress`, `blocked`, `cancelled` |
| `in_progress` | `todo`, `blocked`, `done`, `cancelled` |
| `blocked` | `todo`, `in_progress`, `cancelled` |
| `done` | `in_progress` |
| `cancelled` | `todo` |

Requesting the current status is an idempotent no-op. Invalid transitions return
`409 invalid_status_transition`.

## UI expectations

- Preserve the dark cyberpunk theme, responsive layout, and Space Grotesk/DM Sans typography unless
  a task explicitly changes the design direction.
- A card title opens the story editor. Keep drag-and-drop movement and the editor's accessible
  movement buttons in sync.
- HTMX story writes replace `#board` with `frontend/templates/partials/board_columns.html`.
- After an HTMX board swap, reapply browser-local filters and visible-lane state.
- Tag filters are session-local and match any selected tag.
- Lane visibility is stored per project in `localStorage`; at least one lane must remain visible.
- Hidden lanes expand the remaining columns and must not mutate or delete their stories.
- Keep repository links restricted to complete HTTP(S) URLs and render them with safe external-link
  attributes.
- Preserve confirmation before story deletion.

When adding a domain capability, implement and test the JSON API behavior first, then have the UI
call the same service. Do not duplicate server validation in JavaScript as an authority.

## Database and data safety

The user's existing projects and stories are valuable. Preserve them.

- Never run `docker compose down --volumes`, drop tables, truncate data, delete the database, or wipe
  a volume unless the user explicitly requests destructive cleanup.
- Do not replace an existing database just to simplify development or testing.
- Tests already use temporary SQLite databases and must not point at the development PostgreSQL
  database.
- For schema changes, edit `backend/app/models.py`, generate and inspect a new Alembic revision, and
  make the migration safe for existing rows.
- Never rewrite an already-shared migration. Add a new revision.
- Verify PostgreSQL-specific changes with Compose; passing SQLite tests is not sufficient evidence
  for constraints or migrations.
- Preserve unrelated working-tree changes. Do not reset or clean the repository to obtain a tidy
  diff.

## Testing expectations

Add or update tests for every behavior change. Place tests by public behavior:

- API resource and error behavior in `backend/tests/test_*_api.py`.
- Server-rendered and HTMX behavior in `backend/tests/test_ui.py`.
- Health behavior in `backend/tests/test_health.py`.

Before handing work back, run:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Also run `docker compose config -q` when Compose changes, and validate Alembic/Compose behavior when
models or migrations change. For visual changes, inspect the rendered UI at desktop and a narrow
viewport when tooling permits.

## Documentation and completion checklist

Before considering a change complete:

1. Confirm the implementation uses the existing layers and shared service rules.
2. Confirm existing project data is preserved.
3. Add tests that would fail without the change.
4. Run checks appropriate to the risk of the change.
5. Update `README.md`, `docs/api.md`, `docs/user-guide.md`, `docs/architecture.md`, or
   `docs/development.md` when their claims are affected.
6. Report what changed, what was verified, and any limitation that remains.

## Current security boundary

Authentication, authorization, multi-tenancy, rate limiting, and CSRF protection are not
implemented. Do not describe the application as production-ready or expose it to an untrusted
network. Treat deletion and future agent write access as high-impact operations requiring explicit
scoping and, where appropriate, human confirmation.
