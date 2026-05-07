# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

# uv z oficiálního image (rychlejší než pip install uv)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 1. Nejdřív instaluj jen závislosti (cached layer pokud se pyproject/lock nemění)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# 2. Až teď zkopíruj zdroják a doinstaluj sám projekt
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# 3. Data (salaries, embeddings) – pokud volume mount překryje, žádný problém
COPY data/ data/

# Non-root pro běh
RUN groupadd -r app && useradd -r -g app -d /app app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "cv_evaluator.main:app", "--host", "0.0.0.0", "--port", "8000"]
