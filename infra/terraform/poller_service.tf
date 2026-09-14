# Fourth service in milestone 7's per-service rollout, same pattern as
# auth/processing/query-api. Poller is a small stateless HTTP service with a
# single /trigger endpoint (cmd/server/main.go) — Cloud Scheduler calls it
# on a cadence in place of the local poller-scheduler loop
# (docker-compose.yml's own comment on that container). MARKETAUX_API_KEY is
# genuinely optional in the code (main.go only wires the client when the
# token is non-empty) and no such secret exists yet, so it's omitted here.

resource "google_service_account" "poller" {
  account_id   = "poller-service"
  display_name = "Poller service (Cloud Run)"
}

resource "google_secret_manager_secret_iam_member" "poller_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.poller.email}"
}

resource "google_secret_manager_secret_iam_member" "poller_reads_finnhub_api_key" {
  secret_id = google_secret_manager_secret.finnhub_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.poller.email}"
}

resource "google_pubsub_topic_iam_member" "poller_publishes_articles" {
  topic  = google_pubsub_topic.articles.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.poller.email}"
}

resource "google_cloud_run_v2_service" "poller" {
  name                = "poller"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.poller.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/poller:latest"

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
        name  = "PUBSUB_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "PUBSUB_TOPIC_ID"
        value = google_pubsub_topic.articles.name
      }
    }

    scaling {
      min_instance_count = 0
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.poller_reads_database_url,
    google_secret_manager_secret_iam_member.poller_reads_finnhub_api_key,
    google_pubsub_topic_iam_member.poller_publishes_articles,
  ]
}

# Only Cloud Scheduler's own service account may invoke /trigger.
resource "google_service_account" "poller_scheduler" {
  account_id   = "poller-scheduler"
  display_name = "Cloud Scheduler identity for poller /trigger"
}

resource "google_cloud_run_v2_service_iam_member" "poller_invoker_scheduler" {
  name     = google_cloud_run_v2_service.poller.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.poller_scheduler.email}"
}

# Every-minute trigger, matching the local poller-scheduler stand-in loop's
# 60s sleep (docker-compose.yml).
resource "google_cloud_scheduler_job" "poller_trigger" {
  name      = "poller-trigger"
  region    = var.region
  schedule  = "* * * * *"
  time_zone = "Etc/UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.poller.uri}/trigger"
    http_method = "POST"
    oidc_token {
      service_account_email = google_service_account.poller_scheduler.email
    }
  }
}
