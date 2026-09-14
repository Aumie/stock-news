# Terraform manages the secret *containers* and IAM bindings only — never
# the values. Real values are set out-of-band via `gcloud secrets versions
# add`, never through Terraform variables/.tfvars, and never committed to
# the repo (docs/stock-news-digest-requirements.md §10.5).

resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "jwt_signing_secret" {
  secret_id = "jwt-signing-secret"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "finnhub_api_key" {
  secret_id = "finnhub-api-key"

  replication {
    auto {}
  }
}

# Whole-file secret, not a single value: st.login()/st.logout() (app.py)
# read Streamlit's own multi-field secrets.toml ([auth] client_id,
# client_secret, cookie_secret, redirect_uri, server_metadata_url), not
# individual env vars, so this secret's payload is that entire TOML file's
# content, mounted as a volume at .streamlit/secrets.toml (ui_service.tf) —
# same out-of-band value-setting rule as every other secret here. NOTE:
# services/ui/.streamlit/secrets.toml already has real values filled in
# locally (gitignored, never committed) — copy that file's content into this
# secret's first version yourself; not done here to avoid handling the raw
# OAuth client secret value directly.
resource "google_secret_manager_secret" "ui_oauth_secrets" {
  secret_id = "ui-oauth-secrets"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "rabbitmq_url" {
  secret_id = "rabbitmq-url"

  replication {
    auto {}
  }
}

# Auth's service account may only read these two secrets' current values —
# not manage/rotate them, and not read any other secret this project will
# later add (e.g. the LLM API key belongs to query-api, not Auth).
resource "google_secret_manager_secret_iam_member" "auth_reads_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.auth.email}"
}

resource "google_secret_manager_secret_iam_member" "auth_reads_jwt_signing_secret" {
  secret_id = google_secret_manager_secret.jwt_signing_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.auth.email}"
}

resource "google_secret_manager_secret_iam_member" "query_api_reads_rabbitmq_url" {
  secret_id = google_secret_manager_secret.rabbitmq_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.query_api.email}"
}

resource "google_secret_manager_secret_iam_member" "celery_worker_reads_rabbitmq_url" {
  secret_id = google_secret_manager_secret.rabbitmq_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.celery_worker.email}"
}
