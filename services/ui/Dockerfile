FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --shell /bin/false appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "8501", "--server.address", "0.0.0.0"]
