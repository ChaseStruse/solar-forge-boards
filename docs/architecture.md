# Architecture

## Governing rule

The backend owns application behavior; clients present it. The HTMX web interface is one client
alongside future desktop, mobile, and Solar-Forge clients.

```text
JSON API routes ─┐
                 ├─> service functions ─> repository functions ─> PostgreSQL
HTMX UI routes ──┘          │
                            └─> validation, lifecycle rules, activity events
```

## Layer responsibilities

### API and UI presentation

`backend/app/api/` parses JSON into Pydantic commands and returns versioned response envelopes.
`backend/app/ui/` parses HTML forms and renders full Jinja pages or the `#board` HTMX fragment.
Neither layer contains lifecycle or persistence rules.

### Services

`backend/app/services/` owns use cases, business rules, and transaction boundaries. A meaningful
write and its activity event share one transaction. Services are functions rather than stateful
classes; dependencies such as the SQLAlchemy engine are explicit arguments.

### Repositories

`backend/app/repositories/` contains SQLAlchemy Core statements only. Repositories accept an active
`Connection`, do no validation, and do not commit. That keeps transaction ownership in the service
layer.

### Database

`backend/app/models.py` defines SQLAlchemy Core metadata. Alembic revisions under
`backend/migrations/` are the production schema history. PostgreSQL enforces identifiers,
relationships, uniqueness, and valid status values.

The primary relationships are:

```text
projects ──< work_items ──< work_item_tags >── tags
    │              │
    └──────────────┴──< activity_events
```

Tags belong to one project. Service validation prevents a story from receiving a tag from another
project. Deleting a work item cascades its tag assignments and sets historical activity references
to null; deleting a project would cascade its work items, tags, and activity. Project deletion is not
exposed publicly today.

### Browser behavior

`frontend/static/js/board.js` owns presentation-only state and interactions: drag and drop, tag
filtering, view presets, and lane visibility. Tag filters last for the current page session. Visible
lanes are stored in browser `localStorage` under the project ID. Neither mechanism changes database
state; only HTMX forms call server-owned transitions and writes.

## Domain decisions

Work items begin in `todo`. Transitions are explicit commands rather than generic status edits:

| Current status | Allowed targets |
| --- | --- |
| `todo` | `in_progress`, `blocked`, `cancelled` |
| `in_progress` | `todo`, `blocked`, `done`, `cancelled` |
| `blocked` | `todo`, `in_progress`, `cancelled` |
| `done` | `in_progress` |
| `cancelled` | `todo` |

`PATCH /work-items/{id}` cannot alter status, so every lifecycle change passes through the
transition policy and produces an event.

Activity events are append-only application facts. A service records a meaningful write and its
event in the same database transaction. Deleting a story preserves its earlier events and adds a
deletion event containing the former ID, title, and status. Activity currently supports audit
history and provides the seam for later notifications, webhooks, analytics, and agent context.

New projects receive their four default tags in the same transaction as project creation. Work-item
responses embed their ordered tag objects so agent and UI clients do not need an N+1 lookup pattern.

## Dependency and extension rules

- Routes may import services and schemas, never repositories directly.
- Services may import repositories, domain rules, and schemas.
- Repositories may import only database tables and SQLAlchemy primitives.
- Templates receive presentation-ready data and do not encode authoritative rules.
- New clients should use `/api/v1`, not HTMX endpoints.
- Cross-cutting behavior belongs in shared helpers only when it has at least two genuine consumers.

Authentication can later resolve an actor in the API/UI layer and pass an actor context to services.
Authorization belongs in services so every client receives identical enforcement.

## Runtime and deployment shape

The Flask application factory creates one SQLAlchemy engine and registers health, API, and UI
blueprints. Docker Compose runs PostgreSQL, a one-shot Alembic migration service, and the development
web server. The image's default command runs Gunicorn as a non-root user for deployment behind an
external database and reverse proxy.

Google Fonts and HTMX are currently loaded from public CDNs by the base template. A browser needs
network access to those origins for the intended typography and HTMX interactions; production
hardening may vendor and pin these assets locally.
