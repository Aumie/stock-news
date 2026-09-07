package poller

import "testing"

func TestCallsPerCycle(t *testing.T) {
	cases := []struct {
		overflowCount int
		want          int
	}{
		{0, 0},
		{1, 1},
		{50, 1},
		{51, 2},
		{100, 2},
		{101, 3},
	}
	for _, c := range cases {
		got := CallsPerCycle(c.overflowCount)
		if got != c.want {
			t.Errorf("CallsPerCycle(%d) = %d, want %d", c.overflowCount, got, c.want)
		}
	}
}

func TestCadenceMinutes(t *testing.T) {
	// Batch size raised to 50/call after a live check found no hard limit at
	// 98 symbols/request (decision_log_claude.md, milestone 3) — cadence
	// scales proportionally with calls/cycle, derived from the 100/day
	// budget: 24h / (calls/cycle * cyclesPerDayBudget).
	cases := []struct {
		overflowCount int
		wantMinutes   float64
	}{
		{0, 0},
		{50, 14.4}, // 1440 min/day / 100 calls = 14.4 min/call
		{51, 28.8}, // 2 calls/cycle -> half the cycles fit in the same call budget
		{100, 28.8},
		{101, 43.2}, // 3 calls/cycle
	}
	for _, c := range cases {
		got := CadenceMinutes(c.overflowCount)
		if !almostEqual(got, c.wantMinutes, 0.01) {
			t.Errorf("CadenceMinutes(%d) = %v, want %v", c.overflowCount, got, c.wantMinutes)
		}
	}
}

func almostEqual(a, b, tolerance float64) bool {
	diff := a - b
	if diff < 0 {
		diff = -diff
	}
	return diff <= tolerance
}

func TestCadenceMinutes_ZeroOverflowMeansNoMarketauxCallsNeeded(t *testing.T) {
	if got := CadenceMinutes(0); got != 0 {
		t.Errorf("expected 0 cadence (no calls needed) for zero overflow, got %v", got)
	}
}
