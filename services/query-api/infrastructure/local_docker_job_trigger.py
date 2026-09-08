from __future__ import annotations

import subprocess

import structlog

logger = structlog.get_logger()


class LocalDockerJobTrigger:
    """Local-dev stand-in for the GCP Cloud Run Jobs API (decision_log.md):
    shells out to `docker compose run` to start a one-off daily-batch
    execution scoped to a single symbol. Requires the Docker socket mounted
    into this container and the Docker CLI installed alongside it — both
    local-only, never present in the cloud image (docker-compose.yml).
    """

    def __init__(
        self,
        project_name: str,
        service: str = "daily-batch",
        compose_file: str = "/workspace/docker-compose.yml",
    ) -> None:
        self._project_name = project_name
        self._service = service
        self._compose_file = compose_file

    def trigger_for_symbol(self, symbol: str) -> None:
        args = [
            "docker",
            "compose",
            "-f",
            self._compose_file,
            "-p",
            self._project_name,
            "--profile",
            "batch",
            "run",
            "--rm",
            self._service,
            "--symbol",
            symbol,
        ]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            # Best-effort trigger: the symbol is already saved to the
            # watchlist by this point, so a failed price backfill must not
            # fail the add-symbol request. The daily sweep will pick this
            # symbol up regardless (decision_log.md).
            logger.warning(
                "local_docker_job_trigger.failed",
                symbol=symbol,
                returncode=result.returncode,
                stderr=result.stderr[-2000:],
            )
        else:
            logger.info("local_docker_job_trigger.succeeded", symbol=symbol)
