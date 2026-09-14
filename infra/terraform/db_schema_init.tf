# One-time schema init against the real Supabase Postgres instance —
# infra/postgres/init.sql only auto-applies to local Docker Postgres via the
# image's own /docker-entrypoint-initdb.d convention (its own header
# comment); the cloud database has no equivalent, and this session's first
# real daily-batch run against it failed with
# `relation "watchlist" does not exist` (confirmed live, not local).
#
# database_url is a plain Terraform variable, not a Secret Manager
# reference, specifically so the real connection string never has to pass
# through any .tf file or Terraform state that gets shared — it only lives
# in your own gitignored terraform.tfvars (see terraform.tfvars.example)
# and in this apply's local-exec environment. `sensitive = true` keeps it
# out of plan/apply console output.
variable "database_url" {
  description = "Real Supabase Postgres connection string, for the one-time schema init only. Set in terraform.tfvars (gitignored), never committed."
  type        = string
  sensitive   = true
}

resource "null_resource" "db_schema_init" {
  # Re-runs only when init.sql's own content changes — not on every apply.
  triggers = {
    init_sql_hash = filesha256("${path.module}/../postgres/init.sql")
  }

  # Runs psql via the postgres Docker image rather than requiring a local
  # psql install — this machine doesn't have one, and every other DB
  # operation this session already goes through Docker. init.sql's content
  # is piped over stdin instead of volume-mounted — bind-mounting a Windows
  # path (C:/...) into Docker under Git Bash's `sh -c` misparses the
  # host:container split on the drive letter's own colon (found live: `docker:
  # invalid mode: /sql"`), and stdin sidesteps path translation entirely.
  provisioner "local-exec" {
    command     = "docker run --rm -i -e PGSSLMODE=require postgres:16-alpine psql \"$DATABASE_URL\" < \"${path.module}/../postgres/init.sql\""
    interpreter = ["bash", "-c"]
    environment = {
      DATABASE_URL = var.database_url
    }
  }
}
