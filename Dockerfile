FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DIR=/app

WORKDIR $APP_DIR

FROM base AS builder

#RUN apt-get update \
# && apt-get install -y --no-install-recommends build-essential \
# && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /bin/uvx

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project

COPY . .

FROM base AS production

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:${PATH}"

# Create database directory and set permissions for app user
RUN mkdir -p /app/db && \
    groupadd -r app && \
    useradd -r -g app -m app && \
    chown -R app:app /app/db && \
    chmod -R u+rw /app/db && \
    chown -R app:app /app

ENV HOME=/home/app

USER app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]



