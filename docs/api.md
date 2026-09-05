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
reference, alongside their internal UUID. They embed complete tag objects in `tags`, allowing a
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
response used by the board.

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

Activity is append-only through the public application behavior. There is no pagination or event
delivery endpoint yet.

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
