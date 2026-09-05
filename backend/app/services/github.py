"""Repository views reuse persisted project settings without holding database transactions."""

from uuid import UUID

from sqlalchemy import Engine

from backend.app.integrations.github import GitHubClient
from backend.app.schemas.github import GitHubRepository
from backend.app.services.projects import get_project


def project_repositories(
    engine: Engine,
    project_id: UUID,
    client: GitHubClient,
) -> list[GitHubRepository]:
    """Resolve the project before performing any external requests."""
    project = get_project(engine, project_id)
    return client.repositories(project["repository_urls"])
