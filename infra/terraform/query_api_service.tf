# Third service in milestone 7's per-service rollout (decision_log_claude.md),
# same pattern as auth_service.tf/processing_service.tf. RABBITMQ_URL now
# points at the real CloudAMQP instance (celery_worker_service.tf runs the
# actual worker). COMPOSE_PROJECT_NAME stays permanently omitted regardless
# — it selects LocalDockerJobTrigger, which shells out to `docker compose`
# against a socket that doesn't exist in this image at all; build_job_trigger()
# already degrades to None with a warning when it's unset, which is the
# correct behavior here until a CloudRunJobTrigger is implemented (the
# immediate per-symbol price/daily_symbol_features rebuild on watchlist-add
# stays a known gap — the news backfill itself doesn't depend on it and now
# works, but the price-rebuild half still waits for the next scheduled
# daily-batch sweep).

resource "google_service_account" "query_api" {
  account_id   = "query-api-service"
  display_name = "Query API service (Cloud Run)"
}

resource "google_secret_manager_secret_iam_member" "query_api_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_secret_manager_secret_iam_member" "query_api_reads_jwt_signing_secret" {
  secret_id = google_secret_manager_secret.jwt_signing_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_secret_manager_secret_iam_member" "query_api_reads_anthropic_api_key" {
  secret_id = google_secret_manager_secret.anthropic_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_secret_manager_secret_iam_member" "query_api_reads_finnhub_api_key" {
  secret_id = google_secret_manager_secret.finnhub_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.query_api.email}"
}

# See secrets.tf for the query_api_reads_rabbitmq_url grant (co-located with
# the other secret IAM grants for celery_worker/query_api together).

resource "google_cloud_run_v2_service" "query_api" {
  name     = "query-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  # Same reasoning as processing_service.tf — a failed first revision here
  # would otherwise be blocked from replacement by deletion_protection even
  # though nothing real served traffic yet.
  deletion_protection = false

  template {
    service_account = google_service_account.query_api.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/query-api:latest"

      ports {
        container_port = 8002
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
        name = "JWT_SIGNING_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jwt_signing_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
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
        name  = "LOG_ENV"
        value = "prod"
      }

      env {
        name  = "PROCESSING_URL"
        value = google_cloud_run_v2_service.processing.uri
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

      # Selects CloudRunJobTrigger over the local-only LocalDockerJobTrigger
      # (build_job_trigger, backfill_dependencies.py) — COMPOSE_PROJECT_NAME
      # stays permanently unset here, so these are the only signal.
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      # Same memory headroom as processing — query-api also loads the
      # all-MiniLM-L6-v2 SentenceTransformer in-process for pgvector search
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
    google_secret_manager_secret_iam_member.query_api_reads_database_url,
    google_secret_manager_secret_iam_member.query_api_reads_jwt_signing_secret,
    google_secret_manager_secret_iam_member.query_api_reads_anthropic_api_key,
    google_secret_manager_secret_iam_member.query_api_reads_finnhub_api_key,
    google_secret_manager_secret_iam_member.query_api_reads_rabbitmq_url,
    google_cloud_run_v2_service.processing,
  ]
}

# Not publicly reachable (§10.5) — only the UI service's own service account
# may invoke Query API (an exposed query endpoint can trigger a real, billed
# LLM call per request). ui_service.tf now exists, so this points at its
# real service account instead of the earlier placeholder.
resource "google_cloud_run_v2_service_iam_member" "query_api_invoker_ui" {
  name     = google_cloud_run_v2_service.query_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.ui.email}"
}
