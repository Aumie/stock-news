# Cloud Run *Job* (google_cloud_run_v2_job), not a Service — one-shot batch
# run, matching the local docker-compose "batch" profile stand-in
# (docker-compose.yml's own comment: "run on demand ... not a continuously
# running container"). No ingress/invoker binding needed since Jobs aren't
# HTTP-addressable; Cloud Scheduler triggers an execution via the Cloud Run
# Admin API instead of an HTTP endpoint.

resource "google_service_account" "daily_batch" {
  account_id   = "daily-batch-job"
  display_name = "Daily batch job (Cloud Run Job)"
}

resource "google_secret_manager_secret_iam_member" "daily_batch_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.daily_batch.email}"
}

resource "google_cloud_run_v2_job" "daily_batch" {
  name                = "daily-batch"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.daily_batch.email
      # No retries — a half-applied dbt run/price update should surface as a
      # failed execution to investigate, not silently re-run and potentially
      # double-apply (dbt's own table materialization is drop+rebuild so a
      # retry is actually safe, but the Yahoo price fetch step ahead of it
      # is not idempotent-by-design here).
      max_retries = 0

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/daily-batch:latest"

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        # dbt's profiles.yml needs discrete DBT_PG_HOST/PORT/USER/PASSWORD/
        # DBNAME vars, not a single URL — main.py derives and injects those
        # into the dbt subprocess's own env by parsing DATABASE_URL at
        # runtime (dbt_env_from_database_url), so nothing else is needed here.

        # 1Gi, not Cloud Run's 512MiB default — dbt's own subprocess
        # (compiling the project + running against Postgres) proved
        # meaningfully heavier than the default budget for every other
        # Python service this session (processing/query-api both needed the
        # same bump for a lighter in-process model load).
        resources {
          limits = {
            memory = "1Gi"
          }
        }
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.daily_batch_reads_database_url,
  ]
}

# Cloud Scheduler triggers one execution per day via the Cloud Run Admin
# API's :run endpoint (Jobs have no HTTP endpoint of their own to call,
# unlike poller's Service), matching the local "once-daily manual-style
# trigger" design noted in docker-compose.yml's daily-batch comment.
resource "google_service_account" "daily_batch_scheduler" {
  account_id   = "daily-batch-scheduler"
  display_name = "Cloud Scheduler identity for daily-batch job runs"
}

resource "google_project_iam_member" "daily_batch_scheduler_can_run_job" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.daily_batch_scheduler.email}"
}

resource "google_cloud_scheduler_job" "daily_batch_trigger" {
  name      = "daily-batch-trigger"
  region    = var.region
  schedule  = "0 6 * * *"
  time_zone = "Etc/UTC"

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.daily_batch.name}:run"
    http_method = "POST"
    oauth_token {
      service_account_email = google_service_account.daily_batch_scheduler.email
    }
  }
}

# query_api's and celery_worker's own on-add trigger (CloudRunJobTrigger,
# cloud_run_job_trigger.py) calls this same :run endpoint directly from
# application code, replacing local dev's LocalDockerJobTrigger. Needs
# roles/run.developer, not just roles/run.invoker (Cloud Scheduler's own
# grant above) — found live: trigger_for_symbol's containerOverrides call
# got "403 ... Permission 'run.jobs.runWithOverrides' denied", a real gap in
# the invoker role specifically for per-execution argument overrides;
# trigger_full_sweep (no overrides) would have worked fine under plain
# invoker, matching Cloud Scheduler's own always-override-free calls.
# celery_worker needs it too since celery_app.py's task functions
# (backfill_symbol, daily_batch_sweep) are what actually run
# build_job_trigger()'s result, not query_api's own request-handling process.
resource "google_project_iam_member" "query_api_can_run_daily_batch" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_project_iam_member" "celery_worker_can_run_daily_batch" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.celery_worker.email}"
}
