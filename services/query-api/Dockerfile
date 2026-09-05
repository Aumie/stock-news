FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "presentation.api:app", "--host", "0.0.0.0", "--port", "8002"]
