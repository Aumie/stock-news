# Second service in milestone 7's per-service rollout (decision_log_claude.md),
# same pattern as auth_service.tf. QUERY_API_URL is a placeholder for now —
# query-api isn't deployed to Cloud Run yet, so there's no real URL to point
# at; this gets updated once that service lands, matching Auth's own
# accepted placeholder scope in its first pass.

resource "google_service_account" "processing" {
  account_id   = "processing-service"
  display_name = "Processing service (Cloud Run)"
}

resource "google_secret_manager_secret_iam_member" "processing_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processing.email}"
}

resource "google_cloud_run_v2_service" "processing" {
  name     = "processing"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  # The prior revision failed its startup health check (512MiB OOM, fixed
  # below) and never served traffic, so this service is currently tainted —
  # Terraform's default deletion_protection=true otherwise blocks
  # recreating it even though nothing real is being torn down.
  deletion_protection = false

  template {
    service_account = google_service_account.processing.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/processing:latest"

      ports {
        container_port = 8001
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
        name  = "LOG_ENV"
        value = "prod"
      }

      env {
        name = "QUERY_API_URL"
        # Genuine circular dependency: query_api's own PROCESSING_URL depends
        # on this service's URL (query_api_service.tf), so Terraform can't
        # resolve both in one graph via a resource reference. Hardcoded to
        # the real, already-deployed query-api URL instead — Cloud Run URLs
        # are deterministic (project number + region), confirmed stable
        # across every redeploy this session, so this isn't a placeholder.
        value = "https://query-api-921012126198.us-central1.run.app"
      }

      # Real deploy failure found live: Cloud Run's 512MiB default was
      # exceeded during startup — this container loads a SentenceTransformer
      # model (all-MiniLM-L6-v2) in-process, same as query-api, which needs
      # meaningfully more headroom than Auth's small Go binary did
      # (decision_log_claude.md).
      resources {
        limits = {
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.processing_reads_database_url,
  ]
}

# Not publicly reachable (§10.5). Pub/Sub's push subscription invokes
# /pubsub/push (pubsub.tf's processing_invoker_pubsub grant). Separately,
# /articles/ingest is called directly by query_api's own request-handling
# process (the manual "load older" path) AND by celery_worker (the
# watchlist-add background backfill path, infrastructure/processing_ingest_client.py)
# — api-spec.md §6 names Query API's service account for this grant, but the
# actual caller at runtime is whichever process executes
# infrastructure/backfill_dependencies.py's build_backfill_service(), which
# is both. Found live: every backfill-triggered ingest call got a 403 before
# this was wired, since celery_worker's account had no invoker grant at all
# and processing_ingest_client.py sent no auth header either (fixed
# separately, cloud_run_id_token.py).
resource "google_cloud_run_v2_service_iam_member" "processing_invoker_query_api" {
  name     = google_cloud_run_v2_service.processing.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_cloud_run_v2_service_iam_member" "processing_invoker_celery_worker" {
  name     = google_cloud_run_v2_service.processing.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.celery_worker.email}"
}
