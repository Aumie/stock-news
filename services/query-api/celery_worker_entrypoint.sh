#!/bin/sh
# Cloud Run's own celery-worker deployment (celery_worker_service.tf) — the
# worker itself has no HTTP server and never listens on a port, but Cloud
# Run always runs a startup TCP probe against $PORT regardless of whether a
# `ports` block is configured (confirmed live: the worker connected to
# CloudAMQP and went "ready" fine, but Cloud Run killed it every ~4 minutes
# anyway with "Default STARTUP TCP probe failed"). This stub server exists
# solely to satisfy that probe; it has no effect on the worker's real behavior.
python3 -m http.server "${PORT:-8080}" --bind 0.0.0.0 &
exec uv run celery -A infrastructure.celery_app worker \
  --loglevel=info --without-mingle --without-gossip --without-heartbeat
