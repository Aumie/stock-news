package poller

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestTriggerHandler_Returns200OnSuccess(t *testing.T) {
	deps := Deps{
		Watchlist:  &fakeWatchlistReader{},
		Finnhub:    &fakeNewsSource{},
		Publisher:  &fakePublisher{},
		FinnhubCap: 45,
	}
	req := httptest.NewRequest(http.MethodPost, "/trigger", nil)
	w := httptest.NewRecorder()

	TriggerHandler(deps)(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestTriggerHandler_Returns200OnPartialFailure(t *testing.T) {
	// api-spec.md: partial failure (one symbol's fetch failing) still 200s.
	deps := Deps{
		Watchlist: &fakeWatchlistReader{symbols: []WatchedSymbol{
			{Symbol: "BADSYM", WatcherCount: 1, AddedAt: t_(0)},
		}},
		Finnhub:    &fakeNewsSource{errBySymbol: map[string]error{"BADSYM": errors.New("finnhub 500")}},
		Publisher:  &fakePublisher{},
		FinnhubCap: 45,
	}
	req := httptest.NewRequest(http.MethodPost, "/trigger", nil)
	w := httptest.NewRecorder()

	TriggerHandler(deps)(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200 on partial failure, got %d", w.Code)
	}
}

func TestTriggerHandler_Returns500OnHardFailure(t *testing.T) {
	deps := Deps{
		Watchlist:  &fakeWatchlistReader{err: errors.New("db down")},
		Finnhub:    &fakeNewsSource{},
		Publisher:  &fakePublisher{},
		FinnhubCap: 45,
	}
	req := httptest.NewRequest(http.MethodPost, "/trigger", nil)
	w := httptest.NewRecorder()

	TriggerHandler(deps)(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 on hard failure, got %d", w.Code)
	}
}

func TestTriggerHandler_RejectsNonPOST(t *testing.T) {
	deps := Deps{Watchlist: &fakeWatchlistReader{}, Finnhub: &fakeNewsSource{}, Publisher: &fakePublisher{}, FinnhubCap: 45}
	req := httptest.NewRequest(http.MethodGet, "/trigger", nil)
	w := httptest.NewRecorder()

	TriggerHandler(deps)(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 for GET, got %d", w.Code)
	}
}
