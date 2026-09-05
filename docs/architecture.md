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
classes; dependencies such as the SQLAlchemy engine are explicit arguments. Write use cases can
also participate in an existing service-owned connection transaction. Shared helpers enforce archive
and revision preconditions, including no-op writes.

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
| `todo` | `in_progress`, `blocked`, `done`, `cancelled` |
| `in_progress` | `todo`, `blocked`, `done`, `cancelled` |
| `blocked` | `todo`, `in_progress`, `done`, `cancelled` |
| `done` | `in_progress` |
| `cancelled` | `todo` |

`PATCH /work-items/{id}` cannot alter status, so every lifecycle change passes through the
transition policy and produces an event.

Each workflow lane has a persisted story priority order. A priority command swaps a story with its
adjacent lane peer in one transaction and records an activity event. Transitioning a story places it
at the end of the destination lane, avoiding ambiguous cross-lane priority comparisons.

Activity events are append-only application facts. A service records a meaningful write and its
event in the same database transaction. Deleting a story preserves its earlier events and adds a
deletion event containing the former ID, title, and status. Activity currently supports audit
history and feeds durable outbox delivery for downstream integrations.

Projects can be archived without deleting their stories, tags, or activity. Archived projects are
readable history, while service-layer checks reject writes consistently for API and HTMX clients.
Acceptance criteria are an ordered JSON collection on a work item so their edits remain part of the
same transactional story update and activity event.

The public JSON API accepts persistent idempotency keys for creations and mutations. A service transaction stores
the domain change, activity, and original successful response atomically and replays it for an identical retry, preventing an agent timeout
from becoming a duplicate write. Projects and stories use monotonically increasing revisions; an
agent can send the returned ETag in `If-Match` to reject a stale write before it overwrites a newer
revision. The server-rendered UI remains compatible by omitting that optional API precondition.

Story references come from an atomically incremented singleton counter, retained after story
deletion. Migration seeds it from the largest existing reference without renumbering stories.
Collection queries apply tag filters and keyset pagination in SQL, with UUID tie-breaking and a
batched tag query for only the returned page.

Full-page and HTMX board rendering share one context builder. Story forms carry search and sort
parameters in their action URLs, preserving the active query across swaps.

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

## Agent tool boundary and tracing

`backend/app/agent/` is a Python HTTP client, with generated tool argument schemas and fixed
`/api/v1` endpoint mappings. It never calls application services or repositories directly. The
trusted host chooses capability scopes and approves proposals outside model arguments. Deletion
and tag creation require a distinct human-confirmation callback. This does not replace future
server authentication and authorization.

API request hooks bind a validated correlation ID to a context variable and return it as a response
header. A shared service helper attaches the ID to activity details before calling the repository
within the existing transaction. Request teardown resets the context, including on errors. This
uses the existing JSON details column and requires no migration or historical backfill.

## GitHub repository integration

Projects store an ordered JSON repository URL list, updated by the existing project service and
transactional audit path. The first URL supplies the story-creation default only when callers omit
the story's repository field; explicit empty values remain empty. This keeps UI and API semantics
consistent without rewriting existing stories.

The Repository tab and public snapshot endpoint call `services/github.py`, which resolves project
settings before making network requests through `integrations/github.py`. No database connection
is held during GitHub requests. The GitHub client holds a server-only environment token, bounds
response sizes, timeouts and concurrency, sanitizes failures, and caches snapshots briefly. Templates
receive typed snapshots and escape release notes as plain text. This is a single trusted local
installation; future hosted credentials and authorization remain a separate design task.


## Transactional outbox

The shared `record_activity` service helper writes the activity event and immutable outbox payload
using the caller's connection. The activity UUID is the outbox primary key, preventing duplicate
capture. A failed enqueue rolls back the domain change and activity, including any idempotency
reservation. No-op commands and response replays bypass capture. Outbox payloads deliberately have
no live story foreign key, so later deletion cannot erase or rewrite an undelivered historical event.

The dispatcher claims one due event in a short transaction with PostgreSQL `FOR UPDATE SKIP LOCKED`,
then performs HTTP outside the transaction. A 60-second lease recovers dead workers. A unique claim
token fences late acknowledgements after another worker reclaims the event. The event's identity
remains stable across those attempts. Transient duplication after a crash is handled by the receiver's
transactional inbox, as described in the Solar Forge guide; no exactly-once network guarantee is made.

Eight unsuccessful attempts enter a visible failed state. Delays begin at five seconds and double
with a one-hour cap. Expired final-attempt leases also become failed. Manual retry grants eight
additional attempts without resetting lifetime counters or changing payloads. Delivery state is
independent of project archive status. The worker has an optional type filter and one installation-wide
HTTP receiver, with no network delivery until explicitly configured and started.

PostgreSQL commit notifications contain no payload. The worker listens before scanning and uses
five-second recovery scans so notifications cannot become a durability dependency. SQLite supports
isolated one-shot dispatch tests; continuous dispatch requires PostgreSQL. API diagnostics and recovery
call the same outbox services as the worker's delivery flow.
