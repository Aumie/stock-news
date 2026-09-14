resource "google_artifact_registry_repository" "services" {
  location      = var.region
  repository_id = "stock-news"
  format        = "DOCKER"
  description   = "Container images for all stock-news Cloud Run services"
}
