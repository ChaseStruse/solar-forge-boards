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
