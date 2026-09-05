# Recommended next steps

This roadmap is a practical sequence for taking Solar Forge Boards from a strong local-first slice
toward a richer planning tool and a useful Solar Forge client. The order prioritizes core
functionality while the application remains local. Security hardening moves up only when the app is
shared beyond a trusted machine or network.

## 1. Finish the core project workflow

- Add project editing and an intentional project archive/delete flow with safeguards.
- Add story search, sorting, pagination, and an activity-history panel in the UI.
- Add assignments, comments, acceptance criteria, and due dates only after agreeing on their domain
  model and API shape.
- Add tag rename/delete with clear behavior for stories that use a removed tag.
- Preserve keyboard and screen-reader workflows as new interactions are added.

Keep new writes behind services and explicit Pydantic schemas; do not make the UI the source of truth.

## 2. Make the API a durable integration contract

- Publish an OpenAPI document generated from the schemas and routes.
- Add cursor pagination and filtering conventions before agents need complete synchronization.
- Add idempotency keys for project, tag, story, and transition writes.
- Add optimistic concurrency (`updated_at` or a revision number) to prevent lost edits.
- Version breaking changes under a new `/api/v2` path rather than silently changing `/api/v1`.

Add contract tests that exercise the same examples used in Solar Forge tooling.

## 3. Deepen Solar Forge integration

- Provide narrowly scoped tools for project context, tag lookup, story planning, and status updates.
- Add correlation IDs so an agent plan, API request, and activity event can be traced together.
- Connect the implemented transactional outbox to a receiver with durable inbox deduplication.
- Define tag taxonomy guidance and specialist routing conventions with the Solar Forge brain.
- Add human confirmation around deletion and tag-vocabulary changes when agent write tools are
  introduced.

## 4. Improve reliability and operations

- Add PostgreSQL integration tests in CI alongside the fast SQLite tests.
- Add structured logs, request IDs, metrics, and error reporting.
- Add backup/restore documentation and a tested migration rollback strategy.
- Pin or vendor the Google Fonts and HTMX assets for offline and production deployments.
- Add a CI pipeline that runs tests, Ruff, mypy, Compose validation, and migration checks.
- Add health/readiness separation if deployment orchestration needs to distinguish process health from
  database readiness.

## 5. Harden before sharing beyond local use

When the app will be exposed outside a trusted local machine or network:

- Add authentication and project-scoped authorization.
- Introduce users, memberships, roles, and service-account identities.
- Add CSRF protection for browser forms and rate limiting for API writes.
- Replace development secrets with required production configuration and document TLS/reverse-proxy
  deployment.
- Add actor identity to activity events so humans and agents are auditable.

## Suggested first milestone

The next focused milestone should be **core planning flow**: project editing, story search and
sorting, an activity-history panel, and the first pass of assignments or acceptance criteria. This
builds directly on the current board without requiring a user-account system first.

After that, make the API contract durable and connect Solar Forge read tools before adding broader
agent write access. Revisit the security section when the app is no longer strictly local.

## Working rule for future changes

For each feature, define the domain rule and API contract first, implement it in a service transaction,
cover it with behavior tests, then add the HTMX presentation. Update `AGENTS.md` and the relevant
documentation whenever the contract or workflow changes.
