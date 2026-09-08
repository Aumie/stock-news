# API spec

Contract for every service boundary in the system. Source of truth is `stock-news-digest-requirements.md` §4/§6 — this doc exists so the actual request/response shapes are written down in one place instead of scattered across prose. Keep this in sync with the code in the same turn a route/RPC changes (backend-service-delivery skill, §4).

Ingress reminder (§6, §10.5): only the UI service is publicly reachable. Every other service requires an authenticated caller — the specific `roles/run.invoker` grant is noted per service below.

---

## Auth service — Go, gRPC

Not a REST API. One Protobuf service, called only by the UI service.

```protobuf
syntax = "proto3";

package auth.v1;

service AuthService {
  // Exchanges a Google-verified identity (from the UI's st.login()) for the app's JWT.
  // Creates the user record on first login (§3), looks it up on subsequent calls.
  rpc ExchangeIdentity(ExchangeIdentityRequest) returns (ExchangeIdentityResponse);
}

message ExchangeIdentityRequest {
  string google_sub = 1;   // already verified by st.login() before this call is made
  string email = 2;
}

message ExchangeIdentityResponse {
  string jwt = 1;
  int64 expires_at_unix = 2;   // 24h from issuance, §3
}
```

- **Auth**: `roles/run.invoker` granted only to the UI service's service account (§6, §10.5). The UI must fetch its own identity token and attach it as gRPC call credentials — this is application code, not automatic like the Scheduler/Pub-Sub invocations below (§6).
- **Errors**: invalid/unverifiable `google_sub` → `INVALID_ARGUMENT`. No retry/backoff contract defined yet — not designed for v1 (§11's "Acknowledged gaps" list).

---

## Poller service — Go, Cloud Run Service (not exposed as a product API)

One HTTP endpoint, triggered only by Cloud Scheduler every minute (§4.2).

| | |
|---|---|
| **Method / path** | `POST /trigger` |
| **Auth** | `roles/run.invoker` granted only to Cloud Scheduler's service account (§6, §10.5) — attached automatically by Scheduler's OIDC config, no application code needed |
| **Request body** | none |
| **Response** | `200 OK` on a completed poll cycle (success or partial success — a single symbol's fetch failing doesn't fail the whole cycle); `5xx` only on a hard failure before any polling started |
| **Side effects** | reads `watchlist` (Postgres), calls Finnhub + Marketaux, publishes to Pub/Sub, writes raw payloads to GCS (§4.2, §6) |
| **Not designed for v1** | no liveness/health signal beyond this response code — §11's "Acknowledged gaps" list |

---

## Processing service — Python, Cloud Run Service (Pub/Sub push target)

| | |
|---|---|
| **Method / path** | `POST /pubsub/push` |
| **Auth** | `roles/run.invoker` granted only to Pub/Sub's push service account (§6, §10.5) — attached automatically by the push subscription's OIDC config |
| **Request body** | standard Pub/Sub push envelope — `{"message": {"data": "<base64 article payload>", "messageId": "...", "publishTime": "..."}, "subscription": "..."}` |
| **Response** | `200 OK` → message acked (dedup + chunk + embed succeeded, or the item was a confirmed duplicate — see §4.3's tier logic); non-2xx → Pub/Sub redelivers per its own retry policy (no dead-letter topic configured yet, §11) |
| **Side effects** | dedup check (3-tier, §4.3), chunk + embed, write to pgvector, write lineage log |

### Direct ingest (news backfill, new v1 feature — see decision_log.md)

| | |
|---|---|
| **Method / path** | `POST /articles/ingest` |
| **Auth** | `roles/run.invoker` granted only to Query API's service account — this is an internal service-to-service call, never public |
| **Request body** | `{ "source", "headline", "published_at", "content", "symbol", "canonical_url"? }` — same article shape as the Pub/Sub payload, no envelope |
| **Response** | `{ "article_id": "..." }` |
| **Side effects** | same as `/pubsub/push` — calls the identical `ProcessArticleUseCase`, just invoked directly instead of via a Pub/Sub envelope. Used by Query API's watchlist-add backfill, a synchronous user-initiated call where the queue's async-decoupling purpose doesn't apply (decision_log.md) |

---

## Query API service — Python, Cloud Run Service

All endpoints require `Authorization: Bearer <jwt>`, verified locally against the shared signing secret (§6) — no per-request call to Auth. `roles/run.invoker` granted only to the UI service's service account (§6, §10.5); the UI must fetch and attach its own identity token here too.

### Watchlist management (§4.1, folded into Query API per §6)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `GET` | `/watchlist` | — | `[{ "symbol": "AAPL", "added_at": "..." }, ...]` | scoped to the caller's own watchlist |
| `POST` | `/watchlist` | `{ "symbol": "AAPL" }` | `201` + the row, or `422` with an error if Finnhub's symbol lookup rejects it (§4.1) | validated against Finnhub only — known gap re: Marketaux coverage, §4.1. On success, synchronously backfills the last 30 days of Finnhub news for the symbol before returning (new v1 feature, decision_log.md) — fetched as 2-3 sequential <=14-day chunks, not one 30-day call (Finnhub's `company-news` endpoint doesn't reliably serve a single 30-day request for a busy symbol, confirmed live). Each chunk is best-effort: a timed-out or failed chunk logs a warning and is skipped rather than failing the request, since Finnhub's endpoint was found to be genuinely unreliable under repeated calls (live-verified — real requests to the same endpoint for the same symbol ranged from 2s to a 60s+ timeout moments apart). A real ~10-60s+ latency for a busy symbol, not a quick CRUD call. Also triggers a one-off daily-batch run scoped to just this symbol, pulling 30 days of OHLCV (Yahoo `range=1mo`, vs. the scheduled sweep's `range=5d`) so the Stats page's 30-day view has real data immediately instead of building it up one day at a time from later sweeps (price/feature-store backfill, new v1 feature, decision_log.md) — fire-and-forget from the caller's perspective: a failed trigger only logs a warning and does not fail the request, since the symbol is already saved and the next scheduled daily sweep will pick it up regardless. Locally this shells out to `docker compose run` via a Docker-socket mount (structurally absent from the cloud image); the cloud path calls the real GCP Cloud Run Jobs API instead, deferred to the milestone 7 cloud migration |
| `DELETE` | `/watchlist/{symbol}` | — | `204` | idempotent |

### Query / digest (§4.4)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `POST` | `/query` | `{ "question": "..." }` | **Streaming** (`StreamingResponse`, chunked, not buffered JSON — §4.4) — token-by-token LLM output, terminated by a final sentinel chunk | Guardrail: if retrieval is empty, the stream's content is an explicit "no news on that" answer, not silence or a generic error (§4.4). If the LLM spend ceiling is hit, the stream instead emits the honest "spending cap reached" message (§4.4) |

**Resolved as of milestone 6**: `/query`'s request body carried an explicit `{ "symbols": [...] }` field through milestones 1-5, since there was no JWT-derived watchlist yet to scope retrieval by. Milestone 6 wires the watchlist repository lookup keyed on the JWT's `sub` (the authenticated user), so `symbols` is now derived server-side from the caller's own watchlist and the request body no longer accepts or needs it — the shape above (`{ "question": "..." }` only) is the current, permanent shape, not a placeholder.

- **Cost note**: this is the one endpoint where public exposure would matter more than anywhere else in the system — each hit can trigger a real LLM API call (§6). The IAM lockdown above is the only thing preventing that from being attacker-controlled.

### Live ingestion feed (§4.5, milestone 6)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `GET` | `/feed?before=<ISO datetime>&before_id=<article_id>` | — (both query params optional, omit for the first page) | `[{ "article_id", "source", "headline", "symbols": [...], "published_at", "ingested_at", "canonical_url" }, ...]` | scoped to the caller's watchlist, most recently **published** first (not most recently ingested — the two diverge for backfilled articles, decision_log_claude.md). `canonical_url` is nullable — a content-hash-deduped article (§4.3) can have no URL. Keyset pagination: pass the last item's `published_at`/`article_id` as `before`/`before_id` to fetch the next older page — real bug found live: a fixed top-50 with no pagination made backfilled older articles structurally unreachable no matter how many times "load more" ran (decision_log.md). **First page only** (no cursor): guarantees each watched symbol at least 10 of its own most-recent articles (per-symbol quota via a window function, merged and re-sorted), not a flat top-50 across every symbol — real bug found live: a high-volume symbol crowded a newly-added, quieter symbol almost entirely out of the feed even though its articles were real and present (decision_log_claude.md). Paged requests (with a cursor) still use the flat top-50 behavior; full per-symbol pagination is a deferred redesign |
| `POST` | `/feed/backfill-more` | — | `{ "total_articles_fetched", "per_symbol": [{ "symbol", "articles_fetched", "from_date", "to_date", "has_more" }, ...] }` | underlying per-symbol backfill primitive — loops `load_more()` over every watched symbol, extending each one's backfilled range another 14 days further back. A symbol with no prior backfill runs an initial 14-day backfill instead of erroring (real bug found live and fixed, decision_log.md). No longer called directly by the UI — superseded there by `/feed/load-older` below, but still used by `POST /watchlist`'s on-add backfill |
| `POST` | `/feed/load-older` | `{ "before"?, "before_id"? }` (both optional, omit for the very first "load older" click) | `{ "items": [...same shape as GET /feed...], "exhausted": bool }` | combines paging and backfilling into one action (user request, decision_log_claude.md) — pages existing Postgres data first (cheap); if that's empty, calls the backfill primitive above for every watched symbol and retries, extending automatically through empty windows up to 6 attempts (~3 months) before giving up with `exhausted: true`. Stops early if a backfill window reports no more history exists at all, rather than exhausting all 6 attempts regardless |

### Stats (§4.6, milestone 6)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `GET` | `/stats` | — | `{ "overview": { "articles_ingested_today", "tickers_tracked" }, "by_symbol": { "<SYMBOL>": { "window_7d": { "total_articles", "rolling_volume": [...], "price_deltas": [...] }, "window_30d": { same shape } } } }` | scoped to the caller's watchlist; per-symbol figures read `daily_symbol_features` (milestone 5). Both a 7-day and a 30-day window are always returned per symbol — no query param — so the UI's per-symbol `7d \| 30d` toggle (each watched symbol has its own, independent of every other symbol's) can switch instantly with no refetch. `total_articles` (sum of `article_count` in the window) replaced the old three-figure `ingestion_lag` block (avg/p50/p95) — user's call, the lag percentiles weren't being used. `rolling_volume`'s average genuinely scales with its window (`rolling_avg` in `window_7d` is a real 7-day rolling average, not the 30-day average truncated to 7 points). Only the 30-day window is actually queried from Postgres per symbol (3 queries, not 6) — the 7-day figures are derived from that same fetch (a second window function for volume, a `FILTER`-based conditional sum for the total, a Python-side tail-slice for price deltas) — a deliberate scaling choice once the per-symbol toggle meant every symbol needs both windows on hand. Cloud cost monitoring was cut from the design entirely (user's call — GCP's own Billing console/budget alerts already do this better than an in-app re-implementation would, and this project is single-tenant/operator-only, see `decision_log.md`) |

---

## UI service — Python (Streamlit)

Not a JSON API — a server-rendered app with its own `st.login()`-gated session. The only publicly reachable service (§6, §10.5). Outbound: calls Auth (gRPC) and Query API (HTTPS) as described above, with explicitly fetched identity tokens on both.

---

## Daily batch job — Python, Cloud Run Job (not an HTTP API)

Invoked via the Cloud Run Jobs execution API, triggered by its own Cloud Scheduler job definition once daily (§4.6, §6) — no custom endpoint to spec. Runs: pull completed OHLCV → finalize `prices` → run `dbt run` for `daily_symbol_features`.
