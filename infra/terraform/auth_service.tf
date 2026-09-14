# First-pass deployment (milestone 7): proves the Terraform + container +
# IAM pattern on the smallest, most self-contained service before repeating
# it for the other five (decision_log_claude.md). DATABASE_URL/
# JWT_SIGNING_SECRET are now sourced from Secret Manager (secrets.tf) —
# Terraform only ever references the secret by name, never the value
# itself; the actual value is set out-of-band via `gcloud secrets versions
# add` (§8/§10.5 of the requirements doc).

resource "google_service_account" "auth" {
  account_id   = "auth-service"
  display_name = "Auth service (Cloud Run)"
}

resource "google_cloud_run_v2_service" "auth" {
  name     = "auth"
  location = var.region
  # Request-only CPU, min-instances=0 — every service in this project's
  # design defaults to scale-to-zero (§8), Auth is no exception.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.auth.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}/auth:latest"

      ports {
        container_port = 50051
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
    }

    scaling {
      min_instance_count = 0
    }
  }

  depends_on = [
    google_artifact_registry_repository.services,
    google_secret_manager_secret_iam_member.auth_reads_database_url,
    google_secret_manager_secret_iam_member.auth_reads_jwt_signing_secret,
  ]
}

# Not publicly reachable (§10.5) — only the UI service's own service account
# may invoke Auth (api-spec.md §6: "UI must fetch its own identity token and
# attach it as gRPC call credentials"). ui_service.tf now exists, so this
# points at its real service account instead of the earlier placeholder.
resource "google_cloud_run_v2_service_iam_member" "auth_invoker_ui" {
  name     = google_cloud_run_v2_service.auth.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.ui.email}"
}
