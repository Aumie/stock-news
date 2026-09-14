# Fifth service, and the one publicly-reachable one (§10.5) — everything
# else in this project is invoker-locked to a specific caller identity.
#
# clients/auth_client.py fetches its own Google ID token (audience = auth's
# full https:// URL) via Application Default Credentials and attaches it as
# gRPC call credentials over a secure channel (api-spec.md §6) — so
# AUTH_GRPC_ADDR must be the full URL with scheme, not a bare host:port.

resource "google_service_account" "ui" {
  account_id   = "ui-service"
  display_name = "UI service (Cloud Run)"
}

resource "google_secret_manager_secret_iam_member" "ui_reads_oauth_secrets" {
  secret_id = google_secret_manager_secret.ui_oauth_secrets.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_cloud_run_v2_service" "ui" {
  name                = "ui"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.ui.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/ui:latest"

      ports {
        container_port = 8501
      }

      env {
        name  = "QUERY_API_URL"
        value = google_cloud_run_v2_service.query_api.uri
      }

      env {
        name  = "AUTH_GRPC_ADDR"
        value = google_cloud_run_v2_service.auth.uri
      }

      volume_mounts {
        name       = "ui-oauth-secrets"
        mount_path = "/app/.streamlit"
      }
    }

    volumes {
      name = "ui-oauth-secrets"
      secret {
        secret = google_secret_manager_secret.ui_oauth_secrets.secret_id
        items {
          version = "latest"
          path    = "secrets.toml"
        }
      }
    }

    scaling {
      min_instance_count = 0
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.ui_reads_oauth_secrets,
    google_cloud_run_v2_service.query_api,
    google_cloud_run_v2_service.auth,
  ]
}

# Publicly reachable by design (§10.5) — this is the one service end users
# actually load in a browser, authenticating themselves via Google OAuth
# inside the app rather than via Cloud Run IAM.
resource "google_cloud_run_v2_service_iam_member" "ui_invoker_public" {
  name     = google_cloud_run_v2_service.ui.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
