#!/bin/sh
set -eu

uv run alembic upgrade head
exec uv run gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 2 --threads 4 backend.app.wsgi:app

