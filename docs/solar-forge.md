# Solar-Forge integration

Solar Forge Boards is shaped so Solar-Forge can be a first-class client rather than a UI automation
layer.

## Recommended first integration

Give Solar-Forge a narrowly scoped HTTP toolset backed by `/api/v1`:

1. List and get projects to resolve business context.
2. List project tags and list work items, optionally filtering by repeated tag IDs. For a complete
   project synchronization, set `limit`, retain the query controls, and follow `meta.next_cursor`
   until it is null.
3. Get a work item to read its human description, technical description, repository link, status,
   and embedded tag objects.
4. Create work items from approved plans and assign only tags belonging to that project.
5. Update story content or replace its tag set while refining work.
6. Request explicit status transitions as execution progresses.
7. Read recent project activity to explain what changed.

Fetch `GET /api/v1/openapi.json` when generating or validating the client tool definitions. The
document is generated from the API's Pydantic schemas and public route contract; the repository also
tests the same create, retrieve-by-reference, and transition flow used by Solar Forge clients.

Use stable UUIDs as tool arguments and preserve the API error `code` in tool results. An invalid
transition is a domain response the agent can reason about, not an infrastructure failure.

Do not give a broadly autonomous agent the delete endpoint by default. Story deletion is permanent
even though audit events remain, so expose it only through a distinct permission or human-confirmed
tool. Tag creation should likewise be narrower than tag listing to prevent uncontrolled vocabulary
growth.

## Why the API is agent-friendly

- JSON operations are independent of HTML and visual layout.
- Commands are small, typed, and explicit.
- Status cannot be silently mutated through a generic update.
- Activity events make meaningful changes inspectable.
- Work-item responses embed complete, ordered tag objects for classification and routing.
- Project-scoped tags prevent one project's vocabulary from leaking into another.
- Description and technical-description fields separate business intent from implementation context.
- Server-side rules are identical for human and agent clients.

## Context and tagging strategy

Treat the default tags as a starting taxonomy rather than a hard-coded enum. `Coding`, `Spike`,
`Business`, and `Configuration` are ordinary project tags, and people can add more. Resolve tag IDs
from the project before creating or updating a story; never reuse a tag ID from another project.

Multiple `tag_id` list filters use OR semantics. For compound reasoning, retrieve the candidates and
perform any required AND logic in the client. Because each returned story embeds its tags, the agent
can classify results without another tag lookup.

Story collection pagination is opt-in: use a `limit` of 1 through 100, then send the opaque
`meta.next_cursor` alongside the identical `tag_id`, `search`, `sort`, and `direction` controls.
Changing those controls invalidates the cursor. Omitting `limit` retains the full collection response
for interactive board clients.

Use `description` for the user need, business rules, and desired outcome. Use
`technical_description` for architecture, constraints, acceptance details, and implementation notes.
Use `repository_url` only for a complete HTTP(S) link. Keeping these fields distinct makes retrieved
context easier to route to the appropriate Solar Forge brain or specialist.

## Before production agent writes

Add authentication, tenant scoping, service-account identities, and service-layer authorization.
Extend activity events with `actor_id` and an optional correlation ID. Public JSON writes already
accept an `Idempotency-Key`: retain the same key when retrying one intended action, and generate a
new key for a new action. Projects and stories return an ETag; send it as `If-Match` for updates,
transitions, priority moves, archive, and restore actions so a stale agent does not overwrite newer
work.

For autonomous actions, use policy scopes such as `projects:read`, `tags:read`, `tags:write`,
`work_items:write`, `work_items:transition`, and `work_items:delete`. High-impact transitions and
deletions can require a human approval token without changing the public resource model.

The current activity endpoint returns only the 50 newest events and has no cursor. Add pagination or
a durable event cursor before relying on it for complete synchronization.

## Future event delivery

The current activity table is an audit source, not yet a message bus. A transactional outbox can
later publish selected events to Solar-Forge or a queue. The event should be written in the same
transaction as the domain change, then delivered asynchronously with retries and deduplication.

## Python agent tools

`backend.app.agent` provides a framework-neutral tool adapter over the public HTTP API. It requires
no model SDK or new dependencies. A trusted host can supply the returned function definitions to its
model framework and dispatch the model's proposed name/arguments with `call()`:

```python
from backend.app.agent import HttpTransport, SolarForgeTools

board = SolarForgeTools(HttpTransport("http://localhost:8000"))
definitions = board.definitions()
result = board.call("get_story_by_reference", {"reference_number": 6}, correlation_id="plan-6")
```

The default scopes are `projects:read`, `tags:read`, `work_items:read`, and `activity:read`. They expose
`list_projects`, `get_project`, `list_tags`, `list_stories`, `get_story`,
`get_story_by_reference`, and `list_activity`. Story lists accept a `filters` object containing the
API's `search`, `sort`, `direction`, `tag_ids`, `limit`, and `cursor` controls. Pagination metadata is
preserved; follow `meta.next_cursor` with the same filters. Activity remains limited to 50 events.

Hosts can additionally grant `projects:write` (create/update project), `work_items:write`
(create/update story), or `work_items:transition` (transition story). Writes accept a nested
`command` object matching the existing API request schema, plus the endpoint's `project_id` or
`work_item_id` argument where applicable. For example:

```python
from backend.app.agent.tools import READ_SCOPES

# Supply a host-owned function that checks approval for the exact tool name and proposal.
# It may consult a previously approved plan or ask the human through the host's UI.
writer = SolarForgeTools(
    HttpTransport("http://localhost:8000"),
    scopes=READ_SCOPES | {"work_items:write", "work_items:transition"},
    approve_write=host_approval_check,
)
result = writer.call(
    "update_story",
    {"work_item_id": story_uuid, "command": {"title": "Approved revised title"}},
    correlation_id="plan-6",
    idempotency_key="plan-6-update-1",
    etag=current_etag,
)
```

`host_approval_check`, `story_uuid`, and `current_etag` above are supplied by the integration host.
Approval is not a model-visible boolean. Every write requires the appropriate scope and an approving
host callback; denial makes no HTTP request. Unknown arguments are rejected. `tags:write` exposes
`create_tag` and `work_items:delete` exposes `delete_story`; these always use a separate
`confirm_human(name, proposal)` callback that must obtain human confirmation for the exact call.
General write approval cannot authorize either operation. Do not supply an unconditional approval
callback in an autonomous host. These client-side controls are not server authentication or tenant
isolation; use the adapter only with a trusted board origin and trusted host configuration.

Results retain the API's `data` or `error` envelope, including `error.code` and error details.
`meta` adds HTTP `status`, `correlation_id`, and the returned `etag` when available, while preserving
pagination metadata. `scope_denied`, `approval_required`, `unknown_tool`, and local validation errors
occur before transport. HTTP failures retain their server error codes. Network failures return
`transport_error` with status 0; non-JSON server responses return `invalid_api_response` with the
original status. Redirects are not followed and requests use a 15-second timeout by default.

Supply one correlation ID for a plan to connect its requests and activity events. For finer tracing,
use a distinct suffix per request. The adapter generates an ID if omitted. Non-delete writes also
receive an idempotency key (returned in `meta.idempotency_key`) if the host did not supply one.
Prefer supplying and saving the key before dispatch so host crashes can be retried safely. Retain the
same key and payload when retrying an uncertain outcome. There are no automatic retries. A replay
returns the current request's correlation header, while the original activity keeps its original
trace. Deletion has no idempotency or ETag guarantee in the current API and must not be automatically
retried after an uncertain response.

Project commands also accept `repository_urls`, an ordered collection of up to ten GitHub URLs.
The first is the default for story creation when `repository_url` is omitted; pass `""` to opt out.
Clients can read `GET /api/v1/projects/{project_id}/repositories` for cached GitHub stats and release
notes. GitHub credentials remain on the board server.
