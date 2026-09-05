"""Health endpoint tests."""

from flask.testing import FlaskClient


def test_health_reports_database_ready(client: FlaskClient) -> None:
    """The health endpoint checks the database connection."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "connected"}
