variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "stock-news-509321"
}

variable "region" {
  description = "GCP region for all resources — single region, no multi-region/failover per the project's single-environment scope"
  type        = string
  default     = "us-central1"
}
