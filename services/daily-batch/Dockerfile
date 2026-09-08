FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --shell /bin/false appuser && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["uv", "run", "python", "main.py"]
