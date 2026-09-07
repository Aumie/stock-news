package poller

import "math"

// MarketauxSymbolsPerCall: the spec's original assumption was 20/call,
// conservative because the real per-request limit couldn't be confirmed from
// public docs (§4.2). A live check (decision_log_claude.md, milestone 3) sent
// a real request with 98 symbols and got 200 OK with correct results — no
// hard limit was found, though only that one high value was tested, not the
// actual ceiling. Raised to 50 as a moderate improvement with real headroom
// below the untested boundary, not pushed to the full 98 confirmed working.
const MarketauxSymbolsPerCall = 50

// MarketauxDailyCallBudget is the free-tier daily call cap (§4.2).
const MarketauxDailyCallBudget = 100

const minutesPerDay = 24 * 60

// CallsPerCycle returns how many Marketaux calls one poll cycle needs to
// cover the overflow list, batched at MarketauxSymbolsPerCall symbols/call.
func CallsPerCycle(overflowCount int) int {
	if overflowCount <= 0 {
		return 0
	}
	return int(math.Ceil(float64(overflowCount) / float64(MarketauxSymbolsPerCall)))
}

// CadenceMinutes returns the achievable Marketaux polling cadence given the
// current overflow size, so the 100/day call budget isn't exceeded (§4.2).
// Scales linearly with calls/cycle: more calls needed per cycle means fewer
// cycles fit in the same daily budget, so cadence lengthens proportionally.
func CadenceMinutes(overflowCount int) float64 {
	calls := CallsPerCycle(overflowCount)
	if calls == 0 {
		return 0
	}
	return minutesPerDay / float64(MarketauxDailyCallBudget) * float64(calls)
}
