FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY backend ./backend
COPY frontend ./frontend
COPY alembic.ini ./

FROM python:3.14-slim-bookworm AS runtime

RUN groupadd --system solarboards && useradd --system --gid solarboards solarboards
WORKDIR /app
COPY --from=builder --chown=solarboards:solarboards /app /app

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8000
USER solarboards
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "backend.app.wsgi:app"]
