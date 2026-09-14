from __future__ import annotations

import google.auth
import structlog
from google.auth.transport.requests import AuthorizedSession

logger = structlog.get_logger()


class CloudRunJobTrigger:
    """Cloud counterpart to LocalDockerJobTrigger — calls the Cloud Run Jobs
    API's :run endpoint instead of shelling out to `docker compose run`
    (local_docker_job_trigger.py's own docstring already named this as the
    milestone 7 replacement, decision_log.md). Same contract
    (trigger_for_symbol/trigger_full_sweep, both best-effort — never raises,
    since the watchlist-add request must succeed regardless of whether this
    backfill trigger does).

    Auth: query_api's own service account, via Application Default
    Credentials and google-auth's AuthorizedSession (a requests.Session
    subclass that attaches and auto-refreshes an OAuth2 access token) — no
    key file, same ADC mechanism already used for ui's Cloud-Run-to-Cloud-Run
    calls (clients/query_api_auth.py), just a plain access token here rather
    than an ID token since this calls a Google API, not another Cloud Run
    service directly. Needs roles/run.developer on the daily-batch job
    (daily_batch_job.tf's sibling grant) to call :run.
    """

    def __init__(self, project_id: str, region: str, job_name: str = "daily-batch") -> None:
        self._run_url = (
            f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
            f"namespaces/{project_id}/jobs/{job_name}:run"
        )
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._session = AuthorizedSession(credentials)

    def trigger_for_symbol(self, symbol: str) -> None:
        self._run(overrides={"containerOverrides": [{"args": ["--symbol", symbol]}]}, log_context={"symbol": symbol})

    def trigger_full_sweep(self) -> None:
        self._run(overrides={}, log_context={})

    def _run(self, overrides: dict, log_context: dict[str, str]) -> None:
        body = {"overrides": overrides} if overrides else {}
        try:
            response = self._session.post(self._run_url, json=body, timeout=10.0)
            response.raise_for_status()
        except Exception as exc:
            # Best-effort trigger, same as local_docker_job_trigger.py: the
            # symbol is already saved by the time this runs, so a failed
            # price backfill must not fail the add-symbol request — the next
            # scheduled sweep will pick it up regardless. error=str(exc) since
            # this project's structlog rendering doesn't expand exc_info into
            # visible text in Cloud Logging (found live: a first attempt at
            # this logged exc_info=true but no actual traceback anywhere).
            body_text = getattr(getattr(exc, "response", None), "text", None)
            logger.warning("cloud_run_job_trigger.failed", error=str(exc), response_body=body_text, **log_context)
        else:
            logger.info("cloud_run_job_trigger.succeeded", **log_context)
