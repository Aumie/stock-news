FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Docker CLI + compose plugin, local-dev only — LocalDockerJobTrigger shells
# out to `docker compose run` via the socket mounted in docker-compose.yml.
# Never needed in the cloud image (no socket there; CloudRunJobTrigger calls
# the GCP API over HTTPS instead, decision_log.md). Using Docker's own static
# binaries rather than Debian's docker.io package — the latter installs the
# dockerd daemon (unneeded, we only ever talk to the mounted host socket) but
# not the `docker` CLI itself on this base image.
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz | tar -xz -C /tmp && \
    mv /tmp/docker/docker /usr/local/bin/docker && rm -rf /tmp/docker && \
    mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
      https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64 && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Docker Desktop's Linux VM owns /var/run/docker.sock as root:root, so
# appuser needs root's group to read/write it via the bind mount — this
# undoes some of the non-root hardening below, a known, accepted tradeoff of
# the local-only socket-mount approach (decision_log.md).
RUN useradd --create-home --shell /bin/false --gid root appuser && chown -R appuser:root /app
USER appuser

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "presentation.api:app", "--host", "0.0.0.0", "--port", "8002"]
