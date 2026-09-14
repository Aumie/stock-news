FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image at build time — same fix as
# query-api's Dockerfile, for the same reason: a cold-start container
# downloading this from HuggingFace at runtime can hit a 429 rate limit
# whose backoff blows past Cloud Run's startup health-check timeout
# (decision_log_claude.md). HF_HOME is pinned inside /app so the chown
# below covers the cached weights, not just root's default cache dir.
ENV HF_HOME=/app/.cache/huggingface
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Real gap found live: baking the model in wasn't enough on its own —
# sentence-transformers/huggingface_hub still makes HEAD requests to check
# for metadata updates at runtime by default, even with the model already
# cached, and those still hit the same 429 rate limit and its multi-minute
# backoff. HF_HUB_OFFLINE forces the library to use the local cache
# unconditionally, with zero network calls, once the weights are baked in.
ENV HF_HUB_OFFLINE=1

COPY . .

RUN useradd --create-home --shell /bin/false appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "presentation.api:app", "--host", "0.0.0.0", "--port", "8001"]
