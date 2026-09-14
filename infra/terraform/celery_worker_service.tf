# Sixth service in milestone 7's rollout. Same image as query-api
# (identical BackfillService wiring via infrastructure/backfill_dependencies.py,
# docker-compose.yml's own celery-worker entry), different container command.
# Unblocks the watchlist-add news backfill (BackfillService.backfill_on_add),
# which was previously enqueued into a broker that didn't exist in the cloud
# at all — CeleryBackfillQueue now degrades gracefully when that happens
# (celery_backfill_queue.py), but this deploys the real worker so the task
# actually runs instead of just failing to enqueue.
#
# celery-beat is deliberately NOT deployed here — its only scheduled job
# (daily_batch_sweep every 24h, infrastructure/celery_app.py's beat_schedule)
# calls the same JobTrigger.trigger_full_sweep() that daily-batch's own
# Cloud Scheduler trigger already fires directly once a day
# (daily_batch_job.tf), so beat would be a second, redundant path to the
# identical rebuild — not worth its own always-on Cloud Run instance.
#
# KNOWN GAP: COMPOSE_PROJECT_NAME stays unset (must never be set in the
# cloud image, same reasoning as query_api_service.tf), so build_job_trigger()
# still returns None here — the *news* backfill this worker runs now works,
# but the *price*/daily_symbol_features rebuild that would normally follow
# immediately after (JobTrigger.trigger_for_symbol) still only happens on
# daily-batch's next scheduled sweep, until a CloudRunJobTrigger is built.
#
# Not really an HTTP server, but Cloud Run always runs a startup TCP probe
# against $PORT regardless of whether a `ports` block is configured (found
# live: the worker connected to CloudAMQP and went "ready" fine, but Cloud
# Run still killed it every ~4 minutes with "Default STARTUP TCP probe
# failed"). celery_worker_entrypoint.sh starts a trivial stub HTTP server on
# $PORT purely to satisfy that probe, then execs the real celery worker —
# see that script's own comment. min_instance_count = 1 since a Celery
# worker has no requests to scale to zero on.

resource "google_service_account" "celery_worker" {
  account_id   = "celery-worker-service"
  display_name = "Celery worker (Cloud Run, always-on)"
}

resource "google_secret_manager_secret_iam_member" "celery_worker_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.celery_worker.email}"
}

resource "google_secret_manager_secret_iam_member" "celery_worker_reads_finnhub_api_key" {
  secret_id = google_secret_manager_secret.finnhub_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.celery_worker.email}"
}

# See secrets.tf for the celery_worker_reads_rabbitmq_url grant.

resource "google_cloud_run_v2_service" "celery_worker" {
  name                = "celery-worker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account = google_service_account.celery_worker.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/query-api:latest"

      command = ["./celery_worker_entrypoint.sh"]

      ports {
        container_port = 8080
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "FINNHUB_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.finnhub_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "RABBITMQ_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.rabbitmq_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "PROCESSING_URL"
        value = google_cloud_run_v2_service.processing.uri
      }

      env {
        name  = "LOG_ENV"
        value = "prod"
      }

      # Same as query_api_service.tf — celery_app.py's tasks (backfill_symbol,
      # daily_batch_sweep) call the same build_job_trigger()/CloudRunJobTrigger
      # path, since this worker runs the actual Celery task code.
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      resources {
        limits = {
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.celery_worker_reads_database_url,
    google_secret_manager_secret_iam_member.celery_worker_reads_finnhub_api_key,
    google_secret_manager_secret_iam_member.celery_worker_reads_rabbitmq_url,
    google_cloud_run_v2_service.processing,
  ]
}
