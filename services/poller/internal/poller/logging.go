package poller

import (
	"log/slog"
	"os"
)

// NewLogger mirrors the Python services' configure_logging(env) shape
// (services/processing/infrastructure/logging.py): human-readable text
// locally, JSON on Cloud Run, switched on the same LOG_ENV variable every
// service already reads (docker-compose.yml, Terraform's *_service.tf).
func NewLogger(env string) *slog.Logger {
	var handler slog.Handler
	if env == "dev" {
		handler = slog.NewTextHandler(os.Stdout, nil)
	} else {
		handler = slog.NewJSONHandler(os.Stdout, nil)
	}
	return slog.New(handler)
}
