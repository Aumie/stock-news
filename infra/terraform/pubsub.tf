# Real GCP Pub/Sub topic backing poller -> processing, replacing the local
# pubsub-emulator (docker-compose.yml). Poller's own code is unchanged
# between local and cloud (pubsub_publisher.go) — only the environment
# (no PUBSUB_EMULATOR_HOST, a real project) changes, per that file's comment.

resource "google_pubsub_topic" "articles" {
  name = "articles"
}

# Push subscription delivers straight to Processing's /pubsub/push endpoint —
# no bridging relay needed, same as the emulator's push-subscription behavior
# locally (pubsub_publisher.go's comment).
resource "google_service_account" "pubsub_pusher" {
  account_id   = "pubsub-pusher"
  display_name = "Pub/Sub push subscription identity (articles -> processing)"
}

resource "google_cloud_run_v2_service_iam_member" "processing_invoker_pubsub" {
  name     = google_cloud_run_v2_service.processing.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_pusher.email}"
}

resource "google_pubsub_subscription" "articles_to_processing" {
  name  = "articles-to-processing"
  topic = google_pubsub_topic.articles.name

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.processing.uri}/pubsub/push"
    oidc_token {
      service_account_email = google_service_account.pubsub_pusher.email
    }
  }

  depends_on = [google_cloud_run_v2_service_iam_member.processing_invoker_pubsub]
}
