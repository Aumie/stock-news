package poller

import (
	"context"
	"log/slog"
	"net/http"
)

// TriggerHandler is the /trigger endpoint Cloud Scheduler calls every minute
// (api-spec.md). 200 on completed cycle (success or partial success); 5xx
// only on a hard failure before any polling started.
func TriggerHandler(deps Deps, logger *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		result := RunCycle(context.Background(), deps)

		if result.HardFailure != nil {
			logger.Error("poll cycle hard failure", "error", result.HardFailure)
			http.Error(w, "poll cycle failed", http.StatusInternalServerError)
			return
		}

		for _, err := range result.Errors {
			logger.Warn("poll cycle partial failure", "error", err)
		}

		logger.Info("poll cycle complete",
			"polled", result.PolledSymbols,
			"overflow", result.OverflowSymbols,
			"published", result.PublishedArticles,
			"errors", len(result.Errors),
		)

		w.WriteHeader(http.StatusOK)
	}
}
