"""Environment-backed application settings."""

import os

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    """Validated runtime configuration."""

    model_config = ConfigDict(frozen=True)

    database_url: str
    secret_key: str


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://solar_forge_boards:solar_forge_boards@localhost:5432/solar_forge_boards",
        ),
        secret_key=os.getenv("FLASK_SECRET_KEY", "development-only-secret"),
    )
