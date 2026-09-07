# Decision log (user) — quick reference

One-line-per-decision summary of everything settled in `stock-news-digest-requirements.md` — decisions the user made or directed. Each line points to the section with full reasoning — read this to skim, read that to understand *why*.

Implementation-level judgment calls made autonomously while coding (library pinning, bug fixes, data-structure choices, gaps found by running the system) live in `decision_log_claude.md` instead.

## Scope & phasing

- **v1 / v2 split** — v1 (§1–§11) is a complete, shippable portfolio piece on its own; v2 (§12) holds sentiment scoring, pattern detection, and LLM tool-routing, fully designed but deferred, not deleted.
- **"A few weeks" = milestones 1–4 only** (§2, §9) — the MVP checkpoint (RAG loop, auth, dynamic coverage, microservices split). Milestones 5–9 are realistically 6–8 more weeks on top.
- **DDD + TDD everywhere; Clean Architecture's layered folders only for Python, not Go** (§8) — Clean Architecture's domain/application/infrastructure/presentation split is a C#/Java convention, not a requirement of the underlying goal. Python/FastAPI fits it well (typed `Depends()` DI, `Protocol`/ABC interfaces, and each service is already one bounded context so layer-folders don't smear multiple features together). Go fights it — structural interfaces are idiomatically defined at point of use, not in a shared abstraction layer, and Go's package-visibility model resists artificial layer boundaries. Same result (testable, swappable business logic) via different means: full Clean Architecture layering for Processing (real domain logic: dedup tiers), lighter layering for Query API (too thin in v1 to earn full layers), Go-idiomatic package-per-feature + interfaces-at-point-of-use for Auth and Poller (business logic isolated the way Go actually wants it done, not via imported ceremony).

## News ingestion

- **Finnhub primary, Marketaux secondary** (§4.2, §8) — Finnhub: 60 calls/min, no daily cap, real-time. Marketaux: 100/day, batched, used for overflow + cross-source redundancy. Alpha Vantage / NewsAPI ruled out (too rate-limited).
- **Poller: 60s cycle, ~40–45 symbol safe cap** on Finnhub's rate limit, with retry/jitter headroom.
- **Overflow assignment**: rank by distinct watcher count, tie-break by earliest `added_at` — deterministic, not arbitrary. Known gap: no hysteresis, a symbol at the boundary can flip sources between cycles (§4.2).
- **Marketaux's per-request symbol limit and reset-boundary behavior are unverified** — the single highest-risk assumption in the doc; needs a live test call before building the overflow logic (§4.2).
- **No push/webhook on free tiers** — REST polling only; a paid tier would swap the poller for a webhook receiver (§4.2).

## Deduplication

- **Three-tier priority, not two separate mechanisms** (§4.3): canonical URL first → content hash (headline + source + `published_at`, rounded to the minute) → fuzzy headline + published date.
- **Must never key on `source` or `symbol`** — both defeat cross-source/cross-symbol dedup by construction.
- **Content hash must use `published_at`, never `ingested_at`** — a latent bug caught late: hashing on ingestion time would silently break tier 2 entirely (§4.3, §7).
- **DB-level uniqueness constraints, not just application logic** (§4.3, §7) — `canonical_url` and `content_hash` UNIQUE with `ON CONFLICT DO NOTHING`; `article_symbols` composite UNIQUE. Tier 3 (fuzzy match) can't be a hard constraint — accepted low-frequency edge case.
- **Articles are many-to-many with symbols**, not a single `symbol` column (§7) — one article can legitimately cover multiple tickers.

## Auth

- **Google OAuth2 only**, via Streamlit's native `st.login()`/`st.user` (confirmed built-in since 1.42) — the UI handles the OAuth handshake directly, then calls Auth service to exchange the verified identity for the app's JWT (§3, §6).
- **24h JWT expiry, no refresh flow in v1** (deferred to v2) — re-login accepted as the simple option for a low-friction app (§3).
- **Logout is client-side token discard only** — no server-side revocation/blocklist in v1, explicitly acceptable for this threat model (§3).

## Data & storage

- **BigQuery for all structured data** (`prices`, `daily_symbol_features`) — one warehouse, dbt operates there directly (§4.6).
- **Supabase over Neon for pgvector/Postgres, but the margin is narrower than first framed** — the poller's `SELECT DISTINCT symbol FROM watchlist` query runs unconditionally every 60s regardless of news volume, so in practice neither Neon's 5-min autosuspend nor Supabase's 7-day idle-pause would actually fire under normal operation — this isn't a "quiet news day" risk, both handle that fine. The real residual difference: if the *poller service itself* has downtime (bad deploy, Cloud Run incident) longer than 5 minutes, Neon autosuspends and cold-starts on recovery; Supabase's 7-day window absorbs that easily. Neon's database branching is a genuine plus if that workflow matters more than this narrow edge case (§8).
- **`prices` is append-only, no rolling deletion** — storage is negligible even over years; only GCS's raw-article landing zone needs a retention rule (§4.6, §5).
- **`daily_symbol_features`'s date grain is a union of `prices` dates and article-activity dates** — not gated on a `prices` row existing, so weekend/holiday news still gets a row (§4.6).
- **GCS raw landing zone: 7–14 day lifecycle rule** — raw articles are redundant once embedded (§5).

## Architecture & services

- **Real microservices from the start — no monolith-first phase** — considered building v1 as a modular monolith and splitting later, rejected: §2 explicitly wants demonstrated microservices separation, and the per-service IAM/cost/Cloud-Run-shape design already done is specific to separate deployables. Doesn't add work beyond what §9's milestones already plan — just means building each milestone's pieces as their own deployable from day one (§6).
- **Polyglot by design: Go for Auth (+ gRPC) and Poller, Python for everything else** — Python where the ecosystem matters (embeddings, RAG/LLM orchestration, dbt), Go where performance/concurrency matters (identity exchange, concurrent polling). Bounded to 2 of 6 services deliberately — depth over breadth, not Go sprinkled everywhere (§6, §8).
  - **Why gRPC specifically for UI→Auth, and not REST like every other HTTP-facing endpoint in this system**: this is the one boundary that crosses a language split (Python UI calling Go Auth), so the win isn't speed — the call is a single small identity exchange, not a hot path. It's that one `.proto` file generates both sides' client/server code from the same source, so a field rename or type change is a compile error on both sides instead of two hand-written models (a Pydantic model, a Go struct) silently drifting apart. Binary encoding and native streaming are real gRPC properties but genuinely irrelevant at this call's size — a bonus, not the reason it was picked. Every other service boundary in this system stays REST/HTTP specifically because it either faces a browser (UI→Query API needs `st.write_stream`-compatible streaming, which gRPC can't reach without a grpc-web proxy) or doesn't cross a language boundary worth protecting with a generated contract.
  - Query API stays Python even though Go could stream LLM responses fine — it's the most-iterated-on piece of the project, not worth fighting ecosystem maturity on the hardest part.
  - Processing stays Python — local embeddings + v2's FinBERT/TradingPatternScanner are Python-only; switching to API-based embeddings just to unlock Go would trade a free cost for a paid one for no real reason.
  - Daily batch job stays Python regardless of preference — dbt-core is a Python CLI tool.
- **Poller: Cloud Run *Service*, HTTP-triggered by Cloud Scheduler every minute** — went through two corrections to get here: not an always-on service (would cost ~$65/month), not a one-shot Job either (would blow the Secret Manager access budget at every-minute frequency). Services reuse warm instances between triggers; Jobs don't (§4.2, §5, §6, §8).
- **Daily batch: one-shot Cloud Run Job**, triggered once daily — fine at that frequency, no reuse needed (§4.6, §6).
- **Processing: Pub/Sub push subscription, not pull** — push is naturally request-driven/scale-to-zero-friendly; pull would need the same always-on pattern the poller had to avoid (§6).
- **Local queue: superseded — see below.** Originally chose Redis Streams over RabbitMQ (§8 lists both as acceptable local options): this pipeline's actual topology is one producer (poller) and one consumer (processing), no fan-out, no conditional routing between different consumer types, and RabbitMQ's exchange/routing model exists to solve problems this project doesn't have. That reasoning for *Redis over RabbitMQ* still holds — the reversal below is about neither of those, but about not needing a local stand-in broker at all.
- **Local queue, corrected: the GCP Pub/Sub emulator, not Redis Streams or RabbitMQ** — the user asked directly whether anything push-based (matching real Pub/Sub's own delivery model) was available for local dev, which surfaced that Google ships a real Pub/Sub emulator: the actual client/server contract, including genuine push subscriptions (HTTP POST to a given endpoint), not a stand-in needing a bridge. This eliminates the exact problem Redis Streams had (pull-only, no way to push into Processing) without RabbitMQ's unneeded routing machinery either — the emulator calls Processing's `/pubsub/push` endpoint directly, precisely as real Pub/Sub will after the milestone 7 cloud migration, so nothing about that endpoint or the poller's publish call needs to change later, only environment/config. Replaced Redis Streams and deleted the `services/relay` bridging service entirely (it existed only to translate Redis's pull model into an HTTP push call — the emulator makes that translation unnecessary). See `decision_log_claude.md` for the concrete migration trace (exact env vars, config file schema, image chosen, bugs found).
- **Query API also owns watchlist management and JWT verification** — folded in rather than a dedicated watchlist service, consistent with not over-splitting services with no independent lifecycle (§6).
- **UI: Streamlit**, one app, one Cloud Run service — chosen over a full SPA because the project's demonstration value is the backend pipeline, not frontend engineering. SSE was considered and explicitly declined in favor of simplicity (§8).
- **Streamlit's WebSocket reactivity conflicts with scale-to-zero — accepted and bounded, not eliminated.** An idle-but-open browser tab keeps billing until Cloud Run's idle timeout closes it (a documented real-world case shows bot/idle traffic doing this on a public URL). Fixed with two Terraform settings rather than dropping Streamlit: a short request timeout so no connection bills indefinitely, and `max-instances=2` capping worst-case exposure regardless of what hits the public URL (§6, §8).
- **Only the UI service is publicly reachable** — everything else (`--no-allow-unauthenticated`) is IAM-locked to its specific caller: UI's service account → Auth/Query API, Pub/Sub's push account → Processing, Scheduler's account → poller/daily batch (§6, §10.5).
- **UI → Auth/Query API calls need explicit ID-token fetching in application code** — unlike Scheduler and Pub/Sub, which attach tokens automatically; the IAM binding alone doesn't make the calls work, including for the UI's gRPC call to Auth (§6, §10.5).

## Cost & free tier

- **Only accepted paid cost: the LLM/embeddings API** — with a provider-side spend ceiling and an honest "cap reached" message when hit, not a custom monitoring dashboard (§4.4, §5).
- **GCP only, not split with AWS** — AWS restructured its Free Tier in July 2025, making S3/SQS/Fargate a real cost risk for a new account; GCP's Always Free tier is confirmed to persist post-trial (§8).
- **No Airflow** — a 2-step batch chain doesn't justify the operational weight, and Cloud Composer has no free tier (§4.6, §8).
- **No Sentry/Exceptionless** — Cloud Logging (confirmed 50GB/month free) is sufficient at this project's scale; a dedicated error tracker would be reaching for the standard answer, not solving a real need here.
- **Logging: one set of log calls, format switches by environment via `structlog`** — `ConsoleRenderer` locally (readable in `docker compose logs`), `JSONRenderer` on Cloud Run (so Cloud Logging can parse fields). One config decision at process startup, not duplicated logging code or per-call-site branching (§5).
- **No materialized view on the poller's watchlist query** — trivial query, tiny table; would actively work against the "pick up changes promptly" design goal. `daily_symbol_features` *is* materialized as a dbt table — expensive to compute, cheap/frequent to read, the case materialization is actually for (§4.6).
- **Secret Manager: exactly 6 secrets, zero headroom** — Finnhub, Marketaux, OAuth client secret, JWT signing secret, DB connection string, LLM key. Exceeding it costs ~$0.06/version/month, an annoyance not a real budget threat (§8).
- **Terraform manages secret containers and IAM only — never secret values**, which are set out-of-band and never committed or passed through `.tfvars` (§10.5).

## Testing, CI/CD, IaC

- **`dev` branch: local only, Docker Compose, never deploys. `main`: always what's live on GCP.** Feature branches → PR into `dev` → PR `dev` into `main` triggers deploy (§10.1).
- **CI runs on every branch; CD (`terraform apply` + deploy) gated to `main` only** — `terraform plan` on PRs targeting `main` for visibility before merge (§10.3, §10.4).
- **Workload Identity Federation, not a long-lived service account key**, scoped to the `main` branch specifically (§10.4).
- **TDD workflow** — tests for domain-layer logic (dedup, overflow ranking, cadence formula, JWT expiry) written before implementation (§10.2).
- **Push-based CI/CD over pull-based GitOps (ArgoCD), deliberately** — ArgoCD needs a live Kubernetes API to reconcile against; fully-managed Cloud Run has no cluster for that. Pull-based drift detection also matters most with multiple people making untracked manual changes to shared infra — not this project's risk profile (solo dev, sole console access). Right-sized match, not a lesser option (§10.4).
- **Rollback = revert the merge commit, let CD re-apply** — no separate tooling needed; Terraform's declarative model makes this the whole story (§10.4).

## Known gaps — deliberately not fixed in v1, not oversights

- **Symbol validation only covers Finnhub's coverage, not Marketaux's** (§4.1) — a symbol that passes validation but lands in Marketaux's overflow bucket could silently get zero overflow articles if Marketaux doesn't cover it. Low practical impact (major US tickers are covered by both); not worth the extra validation call for v1.
- **No poller liveness/health monitoring** (§11) — the cost dashboard and ingestion-lag logging both assume the poller is producing articles; neither catches a *silent* failure (e.g. a revoked Finnhub key) where it keeps running but produces nothing.
- **No partial-failure/retry/dead-letter semantics across the processing pipeline** (§11) — poller → queue → processing → embed → writes has no defined retry story yet. Matters eventually with this many moving pieces; not designed for v1.

## Deferred to v2 (§12) — designed, not built

- Sentiment scoring (FinBERT, self-hosted)
- Twice-daily batch split (open-capture + close) for intraday price freshness
- 1-year OHLCV backfill on new-symbol add, with gap-detection (not full-symbol-tracked re-backfill)
- Pattern detection (TradingPatternScanner) — nightly precompute at 5 fixed windows (30/90/180/270/360 days) + on-demand computation for any other window
- LLM tool-calling / query routing (`search_news`, `get_structured_data`, `get_pattern`) so chat can answer price/pattern questions, not just news
