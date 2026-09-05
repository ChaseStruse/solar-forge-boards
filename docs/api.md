# JSON API

The API base path is `/api/v1`. Requests and responses use JSON. Successful single resources and
collections are wrapped in a `data` property. Datetimes are ISO 8601 strings and identifiers are
UUIDs.

The generated OpenAPI 3.1 contract is available at `GET /api/v1/openapi.json`. It is generated from
the same Pydantic request and response schemas used by the public routes.

```json
{
  "data": {
    "id": "30b66abf-d2f9-4d87-9556-135c0fde7741"
  }
}
```

Unknown request properties are rejected. The API currently has no authentication, authorization, or
rate limiting and must not be exposed to untrusted networks.

## Safe agent writes

JSON creation endpoints, project updates and archiving, and story updates, transitions, and priority
moves accept an optional `Idempotency-Key` header. Generate a new key for each intended write and
retain it while retrying after a timeout or lost response. Repeating the same endpoint and payload
with the same key returns the original successful response without running the write again. Reusing
a key for a different request returns `409 idempotency_key_reused`. The domain write, activity,
and saved response commit together; a failure rolls them all back so the key can be retried.

Projects and stories include an integer `version`. Their single-resource `GET` responses and write
responses include a quoted `ETag`, such as `"3"`. Agent clients should send that value in
`If-Match` for project updates/archive changes and story updates, transitions, and priority moves.
If another writer has changed the resource first, the request returns `409 version_conflict` instead
of overwriting newer data. This check also applies to no-op commands. An identical idempotent
retry still replays its original response before evaluating the current resource revision. The headers remain optional for compatibility with the browser UI and
existing clients.

## Endpoint summary

| Method | Path | Result |
| --- | --- | --- |
| `POST` | `/api/v1/projects` | Create a project and its four default tags |
| `GET` | `/api/v1/openapi.json` | Get the generated OpenAPI 3.1 contract |
| `GET` | `/api/v1/projects` | List projects in creation order |
| `GET` | `/api/v1/projects/{project_id}` | Get one project |
| `PATCH` | `/api/v1/projects/{project_id}` | Edit an active project's name or description |
| `POST` | `/api/v1/projects/{project_id}/archive` | Archive a project into read-only history |
| `POST` | `/api/v1/projects/{project_id}/restore` | Restore an archived project |
| `GET` | `/api/v1/projects/{project_id}/tags` | List project tags by name |
| `POST` | `/api/v1/projects/{project_id}/tags` | Create a custom tag |
| `POST` | `/api/v1/projects/{project_id}/work-items` | Create a story in Todo |
| `GET` | `/api/v1/projects/{project_id}/work-items` | List project stories in creation order |
| `GET` | `/api/v1/work-items/{work_item_id}` | Get one story |
| `GET` | `/api/v1/work-items/by-reference/{reference_number}` | Get a story by visible reference number |
| `PATCH` | `/api/v1/work-items/{work_item_id}` | Edit story content or replace tags |
| `DELETE` | `/api/v1/work-items/{work_item_id}` | Permanently delete a story |
| `POST` | `/api/v1/work-items/{work_item_id}/transitions` | Request a lifecycle transition |
| `POST` | `/api/v1/work-items/{work_item_id}/priority` | Move a story up or down in its current lane |
| `GET` | `/api/v1/projects/{project_id}/activity` | Get the 50 newest activity events |

## Projects

### Create a project

`POST /api/v1/projects`

```json
{
  "name": "Solar Forge integration",
  "description": "Expose project context to business agents"
}
```

Returns `201`. `name` is required, trimmed, unique, and limited to 120 characters. `description` is
optional and limited to 4,000 characters. Creating a project atomically creates its default tags and
a `project.created` activity event.

### List or get projects

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`

Project responses contain `id`, `name`, `description`, nullable `archived_at`, `created_at`, and
`updated_at`. `PATCH` accepts one or both of `name` and `description`. Archived projects remain
readable but reject project, tag, and story writes with `409 project_archived`; restore them with
the restore endpoint. Archiving and restoring are idempotent and create activity events.

## Tags

### List project tags

`GET /api/v1/projects/{project_id}/tags`

New projects contain `Business`, `Coding`, `Configuration`, and `Spike`. Tags are returned in name
order.

### Create a tag

`POST /api/v1/projects/{project_id}/tags`

```json
{
  "name": "Security",
  "color": "#f4a261"
}
```

Returns `201`. A name is required, trimmed, limited to 60 characters, and case-insensitively unique
inside its project. `color` must be a six-digit hexadecimal color including `#`; it defaults to
`#63f5c4` and is stored in lowercase. The change emits `tag.created`. Tag editing and deletion are
not implemented.

## Work items

### Create a story

`POST /api/v1/projects/{project_id}/work-items`

```json
{
  "title": "Publish tool schema",
  "description": "Describe project and work-item operations",
  "technical_description": "Publish an OpenAPI document from the service schemas.",
  "repository_url": "https://github.com/example/solar-forge",
  "tag_ids": ["2cf9017b-d9f7-4912-a9aa-2e6bec730954"]
}
```

Returns `201`. New work items begin in `todo`. Field limits are:

| Field | Rule |
| --- | --- |
| `title` | Required, trimmed, 1–200 characters |
| `description` | Optional, up to 10,000 characters |
| `technical_description` | Optional, up to 20,000 characters |
| `repository_url` | Optional, up to 2,048 characters, complete HTTP(S) URL |
| `acceptance_criteria` | Optional ordered list of up to 100 nonblank items, each up to 500 characters |
| `tag_ids` | Optional, at most 20 unique UUIDs belonging to this project |

All work-item responses include a globally unique integer `reference_number` for human and agent
reference, alongside their internal UUID. A durable counter prevents deletion from recycling
numbers allocated after migration `20260905_0009`. They embed complete tag objects in `tags`, allowing a
client to classify a story without another request. Use
`GET /api/v1/work-items/by-reference/{reference_number}` when a conversation or pull request only
has the visible number.

### List stories

`GET /api/v1/projects/{project_id}/work-items`

Add repeated `tag_id` query parameters to filter the collection:

```text
/api/v1/projects/{project_id}/work-items?tag_id={coding_tag_id}&tag_id={spike_tag_id}
```

Multiple tag IDs use OR matching: a story is returned when it has any selected tag. Every filter tag
must belong to the project; otherwise the API returns `422 invalid_story_tags`. `search` matches a
story's title, description, or technical description case-insensitively. `sort` accepts
`priority`, `created_at`, `updated_at`, `title`, or `status`, and `direction` accepts `asc` or
`desc`. Without controls, stories are ordered by their persisted priority within each workflow lane.

Add `limit` (from 1 through 100) to opt into cursor pagination. A paginated response includes
`meta.next_cursor`; send that opaque value with the same `tag_id`, `search`, `sort`, and `direction`
parameters to get the next page. `cursor` requires `limit`; changing collection controls or sending
an invalid cursor returns `422 invalid_cursor`. Omit `limit` to retain the complete collection
response used by the board. Filtering and page limits are applied in the database; only returned
stories have their tags loaded. Cursors traverse current data, not a snapshot: if the last story is
deleted or no longer matches the filters, restart traversal after `422 invalid_cursor`.

```text
/api/v1/projects/{project_id}/work-items?search=agent&sort=updated_at&direction=desc&limit=50
```

### Get, edit, or delete a story

- `GET /api/v1/work-items/{work_item_id}`
- `PATCH /api/v1/work-items/{work_item_id}`
- `DELETE /api/v1/work-items/{work_item_id}`

`PATCH` requires at least one of `title`, `description`, `technical_description`, `repository_url`,
`acceptance_criteria`, or `tag_ids`. Only supplied properties are changed. Supplying an empty
`acceptance_criteria` or `tag_ids` array clears that collection; omitting it preserves the value.
`status` is intentionally rejected so lifecycle rules cannot be bypassed.

Delete returns `204` with an empty body. It permanently removes the story. Existing activity events
remain attached to the project with a null `work_item_id`, and a final `work_item.deleted` event
records the former story ID, title, and status.

### Transition status

`POST /api/v1/work-items/{work_item_id}/transitions`

```json
{
  "status": "in_progress"
}
```

Statuses and allowed destinations are:

| Current status | Allowed targets |
| --- | --- |
| `todo` | `in_progress`, `blocked`, `done`, `cancelled` |
| `in_progress` | `todo`, `blocked`, `done`, `cancelled` |
| `blocked` | `todo`, `in_progress`, `done`, `cancelled` |
| `done` | `in_progress` |
| `cancelled` | `todo` |

Requesting the current status is an idempotent no-op. An invalid change returns
`409 invalid_status_transition` with `current` and `target` details. A successful change emits
`work_item.status_changed`.

### Move priority

`POST /api/v1/work-items/{work_item_id}/priority` moves a story one position within its current
workflow lane:

```json
{"direction": "up"}
```

`direction` is `up` or `down`. Moving beyond the first or last story is an idempotent no-op. A
successful swap emits `work_item.priority_changed`. Moving a story to another status places it at
the end of the destination lane's priority order.

## Activity

`GET /api/v1/projects/{project_id}/activity`

Returns at most 50 events, newest first. Each event contains `id`, `project_id`, nullable
`work_item_id`, `event_type`, `details`, and `created_at`. Current event types are:

- `project.created`
- `project.updated`
- `project.archived`
- `project.restored`
- `work_item.created`
- `work_item.updated`
- `work_item.status_changed`
- `work_item.priority_changed`
- `work_item.deleted`
- `tag.created`

Activity is append-only through the public application behavior. Activity pagination is not yet
available. New activity is also captured by the transactional outbox described below.

## Health

`GET /health` is outside `/api/v1`. It executes a database query and returns:

- `200 {"status":"ok","database":"connected"}` when ready.
- `503 {"status":"unhealthy","database":"unavailable"}` when the query fails.

## Errors

Application and HTTP errors use an `error` envelope with a stable `code`:

```json
{
  "error": {
    "code": "not_found",
    "message": "Work item '…' was not found."
  }
}
```

Schema failures return `422 validation_error` with a Pydantic `details` array. Domain validation may
also return `422`, such as `invalid_story_tags`. Unique-name conflicts and invalid transitions return
`409`; unknown resources return `404`. Malformed UUIDs in route paths are handled as `404` by Flask.

## Correlation tracing

Every `/api/v1/` response, including validation and HTTP errors, returns `X-Correlation-ID`.
Clients may supply that header to connect requests to an agent plan; otherwise the server generates
a UUID. IDs must be 1–128 characters, start with an ASCII letter or digit, and contain only ASCII
letters, digits, `.`, `_`, `:`, or `-`. Invalid headers return `422 invalid_correlation_id` with a
fresh valid response trace. IDs are tracing labels, not credentials; do not include secrets.

Activity created by an API request includes the trace in `details.correlation_id`, written in the
same transaction as the domain change. Existing activity and non-API writes may omit it. No-op and
failed commands create no new activity. Idempotent replays echo the retry's trace on the response
and leave the original activity trace unchanged.

## Project GitHub repositories

Project create, read, and update schemas include `repository_urls`: an ordered list of at most ten
complete `https://github.com/owner/repository` URLs. The server trims whitespace, lowercases and
normalizes trailing `/` and `.git`, and removes duplicates while preserving order. Credentials,
query strings, fragments, extra path segments, and non-GitHub hosts are rejected. Creation defaults
to `[]`; updates preserve the list when omitted or null and clear it with `[]`. These changes use
the existing project version checks, idempotency, archive guards, and `project.updated` activity.

When creating a story, omitting `repository_url` defaults it to the project's first repository, or
an empty string when none is configured. Explicit values, including `""`, are honored. Story edits
and existing story links are unaffected by project repository changes.

`GET /api/v1/projects/{project_id}/repositories` returns a `data` array of GitHub snapshots, in
configured order. Each contains `url`, `name`, `description`, nullable `stars`, `forks`, `open_issues`
(including pull requests), `default_branch`, `release`, `error`, and `release_error`. A release has
`name`, `tag`, `url`, `notes`, and nullable `published_at`. GitHub's latest stable release endpoint is
used; draft and prerelease entries are excluded. No published release yields `release: null`.

Upstream errors are sanitized per repository inside a successful collection response; release
failures preserve available repository stats. Unknown projects return 404 before network access.
Requests go only to GitHub's API, with no redirects, a five-second socket timeout, a two-megabyte
response bound, and up to four concurrent repositories. Successful and failed snapshots are cached
for 60 seconds per process (up to 128 entries). Board and activity views do not fetch GitHub stats.


## Event delivery outbox

Every new activity event creates one outbox record in the same transaction as its domain write.
API retries, no-op commands, and failed writes do not create extra events. The immutable payload
has `schema_version: 1` plus the activity fields (`id`, `project_id`, `work_item_id`, `event_type`,
`details`, `created_at`). Its ID is the activity event UUID. Story deletion leaves previously
captured payloads intact, including their original story IDs; payloads are historical facts.
Existing activity from before the outbox migration is not backfilled.

- `GET /api/v1/projects/{project_id}/outbox`: newest 50 records by default; optional `status`
  (`pending`, `processing`, `delivered`, `failed`) and `limit` (1–100). No cursor pagination yet.
- `GET /api/v1/outbox/{event_id}`: one delivery record, or 404.
- `POST /api/v1/outbox/{event_id}/retry`: empty JSON object; grant a failed record eight more
  attempts. Supports `Idempotency-Key`; other states return `409 outbox_not_failed`.

Records expose `id`, `project_id`, `event_type`, `payload`, `status`, lifetime `attempts`,
`attempt_limit`, `next_attempt_at`, `lease_until`, `last_error`, `delivered_at`, and `created_at`.
Internal worker lease tokens are not exposed. Errors are sanitized and never include response
bodies, endpoint credentials, or bearer tokens. Retry preserves the payload, ID, attempt count,
and last error (cleared after successful delivery). It can recover events from archived projects
and does not create another domain activity event or recursively enqueue itself.

Delivery is disabled until an operator configures and starts the separate worker. The web process
never sends queued events. A receiver acknowledges with HTTP 2xx. Retries use the identical payload,
`Idempotency-Key`, and `X-Solar-Forge-Event-ID`; both ID headers equal the event UUID. When present,
the original `details.correlation_id` is forwarded as `X-Correlation-ID`. An optional bearer token
identifies the sending installation to its receiver.

Delivery is **at least once**, not exactly once. Receivers must atomically deduplicate the event ID
with their side effects and return 2xx for an already processed event. A timeout or worker crash can
occur after the receiver commits but before the sender records success. A 409 response is treated
as failure, not as acknowledgement. Ordering is not guaranteed across retries or workers. See the
integration and development guides for receiver requirements and worker configuration.
