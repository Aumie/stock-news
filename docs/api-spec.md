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

---

## Query API service — Python, Cloud Run Service

All endpoints require `Authorization: Bearer <jwt>`, verified locally against the shared signing secret (§6) — no per-request call to Auth. `roles/run.invoker` granted only to the UI service's service account (§6, §10.5); the UI must fetch and attach its own identity token here too.

### Watchlist management (§4.1, folded into Query API per §6)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `GET` | `/watchlist` | — | `[{ "symbol": "AAPL", "added_at": "..." }, ...]` | scoped to the caller's own watchlist |
| `POST` | `/watchlist` | `{ "symbol": "AAPL" }` | `201` + the row, or `422` with an error if Finnhub's symbol lookup rejects it (§4.1) | validated against Finnhub only — known gap re: Marketaux coverage, §4.1 |
| `DELETE` | `/watchlist/{symbol}` | — | `204` | idempotent |

### Query / digest (§4.4)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `POST` | `/query` | `{ "question": "..." }` | **Streaming** (`StreamingResponse`, chunked, not buffered JSON — §4.4) — token-by-token LLM output, terminated by a final sentinel chunk | Guardrail: if retrieval is empty, the stream's content is an explicit "no news on that" answer, not silence or a generic error (§4.4). If the LLM spend ceiling is hit, the stream instead emits the honest "spending cap reached" message (§4.4) |

**Milestone 1 shape, temporary**: until auth (milestone 2) lands, `/query`'s request body also carries `{ "symbols": [...] }` explicitly, since there's no JWT-derived watchlist yet to scope retrieval by (`docs/milestone.md` §1 — "no auth yet"). This field drops once milestone 2's JWT verification is wired in and retrieval is scoped from the caller's own watchlist server-side, matching the shape above exactly.

- **Cost note**: this is the one endpoint where public exposure would matter more than anywhere else in the system — each hit can trigger a real LLM API call (§6). The IAM lockdown above is the only thing preventing that from being attacker-controlled.

---

## UI service — Python (Streamlit)

Not a JSON API — a server-rendered app with its own `st.login()`-gated session. The only publicly reachable service (§6, §10.5). Outbound: calls Auth (gRPC) and Query API (HTTPS) as described above, with explicitly fetched identity tokens on both.

---

## Daily batch job — Python, Cloud Run Job (not an HTTP API)

Invoked via the Cloud Run Jobs execution API, triggered by its own Cloud Scheduler job definition once daily (§4.6, §6) — no custom endpoint to spec. Runs: pull completed OHLCV → finalize `prices` → run `dbt run` for `daily_symbol_features`.
