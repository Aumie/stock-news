package poller

import (
	"context"
	"log"
	"net/http"
)

// TriggerHandler is the /trigger endpoint Cloud Scheduler calls every minute
// (api-spec.md). 200 on completed cycle (success or partial success); 5xx
// only on a hard failure before any polling started.
func TriggerHandler(deps Deps) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		result := RunCycle(context.Background(), deps)

		if result.HardFailure != nil {
			log.Printf("poll cycle hard failure: %v", result.HardFailure)
			http.Error(w, "poll cycle failed", http.StatusInternalServerError)
			return
		}

		for _, err := range result.Errors {
			log.Printf("poll cycle partial failure: %v", err)
		}

		log.Printf(
			"poll cycle complete: polled=%d overflow=%d published=%d errors=%d",
			result.PolledSymbols, result.OverflowSymbols, result.PublishedArticles, len(result.Errors),
		)

		w.WriteHeader(http.StatusOK)
	}
}
