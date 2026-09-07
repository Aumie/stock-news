# Milestones — progress tracking

Tracks progress against `stock-news-digest-requirements.md` §9. Update checkboxes as work lands — this is the "where are we" doc, not a place to re-explain decisions (that's `decision_log.md`).

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

**Current milestone:** 7 (Cloud migration) — next up

---

## 1. Core RAG loop — done
Static ingestion of a fixed symbol list (unstructured news) → embed → query, working end to end.

- [x] Processing service skeleton (domain/dedup logic, chunking, embeddings)
- [x] Query API skeleton (retrieval + LLM call, no auth yet)
- [x] Static/hardcoded symbol list ingestion (stand-in for the real poller)
- [x] Local pgvector via docker-compose
- [x] End-to-end check: ingest a few articles → embed → ask a question → get a grounded answer (LLM stubbed by default for local/cost-sensitive dev — see `decision_log_claude.md`; retrieval and grounding verified for real against live Postgres/pgvector)

## 2. Auth — done
Google OAuth2 login, user + watchlist tables.

- [x] Auth service (Go + gRPC) — `ExchangeIdentity` RPC, JWT issuance (`api-spec.md`) — verified live: real gRPC calls against a running container, real Postgres inserts/lookups, correct `INVALID_ARGUMENT` on bad input
- [x] `users` + `watchlist` tables (`er-diagram.md`) — already existed from milestone 1's `init.sql`
- [x] Streamlit `st.login()` integration — verified live with real Google Cloud Console OAuth credentials: clicking "Log in with Google" correctly redirects to Google's real sign-in page. Full round-trip (completing sign-in → callback → UI exchanging identity with Auth) is the user's own action, not automated here (`decision_log_claude.md`)
- [x] JWT verification in Query API (local, no call-back to Auth) — verified live end-to-end: a JWT issued by the real Auth container is accepted by Query API's `/query`, a missing/garbage token gets a real `401`, no call back to Auth involved

## Known follow-up from milestone 2

- `/query`'s `symbols` field (milestone 1's temporary shape, api-spec.md) still hasn't been replaced by server-side watchlist-scoped retrieval — that needs a watchlist repository query keyed on the JWT's user id, which is separate functionality from "verify a JWT" and wasn't in milestone 2's checklist. Deliberately deferred, not forgotten — see `api-spec.md`'s note.

## 3. Dynamic symbol coverage — done
Poller re-reads distinct watched symbols each cycle and adjusts its polling set automatically.

- [x] Poller service (Go) — Finnhub client, overflow-assignment rule, cadence-scaling formula. Overflow ranking and cadence formula are pure/fully unit-tested. Finnhub client verified live end-to-end once a key was provided: a real poll cycle for AAPL returned 13 real news items, correctly parsed and published through the full real pipeline (`decision_log_claude.md`)
- [x] Marketaux client (overflow lane) — built and verified live once a key was provided: a real batched call to `api.marketaux.com/v1/news/all` correctly authenticated, parsed real articles (including non-ASCII headlines), and correctly extracted per-article matched symbols from `entities` (a response can include entities beyond the queried symbols — confirmed live, filtered out in `cycle.go` so untracked tickers never get ingested)
- [x] **Live check before building overflow logic further**: Marketaux's per-request symbol limit and reset-boundary behavior (§4.2) — **done**. Real finding: the spec's conservative 20-symbols/call assumption was far more cautious than necessary — a real request with 98 symbols succeeded fully with no error, though the actual ceiling (if any) above that wasn't found. Batch size raised to 50/call (user's explicit choice, moderate increase with headroom below the untested boundary — see `cadence.go`, `decision_log_claude.md`). Reset-boundary behavior remains **genuinely undocumented and unconfirmed** even after the live check (no reset-timestamp header exists in Marketaux's response) — this can only be resolved by watching the quota counter reset over real wall-clock time or contacting Marketaux support, not from a single call
- [x] Cloud Scheduler trigger design validated locally (simple interval loop stands in for it in docker-compose) — verified live: the `poller-scheduler` sidecar fires a real `POST /trigger` every 60s, confirmed repeating, poller correctly processes each real cycle and returns `200`
- **Full pipeline verified live end-to-end with both real sources**: a real overflow scenario (Finnhub cap forced to 0) correctly routed a watched symbol to Marketaux, fetched real articles, and published them through the complete real pipeline (dedup → embed → Postgres). The deliberate same-story-via-both-sources dedup collision is exercised properly under milestone 4, below.

## 4. Microservices split — MVP checkpoint — done
Separate poller, processing, and query services communicating via queue.

- [x] Pub/Sub (or local equivalent) wiring, poller → processing — initially built with Redis Streams + a small bridging relay service, then **corrected to the real GCP Pub/Sub emulator** once the user asked whether any local option supported genuine push delivery like real Pub/Sub (`decision_log.md`'s "Local queue, corrected" entry). The emulator speaks the actual Pub/Sub client/server contract, including real push subscriptions — it calls Processing's unchanged `/pubsub/push` endpoint directly, with no bridging service of any kind. Verified live multiple times, including a real Finnhub poll cycle publishing 15 articles that were pushed by the emulator itself (confirmed via the emulator's own container IP in Processing's access logs) straight through to Postgres, and an automated integration test (`services/poller/internal/poller/pubsub_publisher_test.go`) against the real emulator
- [x] Three-tier dedup implemented (`content_hash` on `published_at`, `canonical_url`, fuzzy headline) + DB constraints — built in milestone 1, DB constraints hardened during the smell audit (`ON CONFLICT DO UPDATE ... RETURNING`, verified against a real 10-thread concurrent-write test)
- [x] Cross-source dedup actually exercised (same story via Finnhub and Marketaux) — deliberately engineered live test: two crafted articles (same real-world story, different headline punctuation/case, no canonical URL, ~45s apart) published as `finnhub` then `marketaux` through the real pipeline correctly collapsed to exactly one `articles` row, one `article_symbols` link, and (see below) one real embedding
- [x] **MVP checkpoint reached** — milestones 1-4 are done and verified against real infrastructure throughout, matching the spec's own honest "few weeks" target (§2)

**Major bug found and fixed during this milestone's own verification, not before**: the deliberate cross-source dedup test above first surfaced that `find_by_fuzzy_key` matched a newly-inserted article against itself, silently discarding embeddings for every article without a `canonical_url` (introduced by the earlier smell-audit fix #6, caught within the same working session — no real ingested data was lost, see `decision_log_claude.md` for the full trace and blast-radius check). Fixed, covered by a new regression test that's confirmed to fail without the fix, and reverified live: the same cross-source scenario now correctly produces a real embedding.

## 5. Structured pipeline & feature store — done
Cloud Scheduler + Cloud Run batch job pulls daily closing price/volume; dbt model into `daily_symbol_features`; complex-SQL stats queries.

- [x] Daily batch job (`services/daily-batch`, Python) — Cloud Run Job shape: a one-shot `docker compose --profile batch run --rm daily-batch`, not a long-running service, matching the spec's once-daily cadence (§4.6). Reads distinct watched symbols from `watchlist`, pulls OHLCV, upserts `prices`, then shells out to real `dbt run` + `dbt test`. Verified live end-to-end inside its actual container: a real Yahoo Finance fetch, a real Postgres write, a real dbt run producing `daily_symbol_features`, all 4 dbt tests passing, container exiting cleanly
- [x] **Live check surfaced a real spec-breaking finding**: Finnhub's candle endpoint (the spec's original OHLCV source) returned a real `403` — it's now Premium-gated, confirmed against the docs and a live call with the project's own key. Stooq (the first free alternative tried) is now blocked by a JS proof-of-work anti-bot challenge, unusable from a server-side job without scripted evasion. **Corrected to Yahoo Finance's chart API** (no key, verified live with a plain browser `User-Agent`) — see `decision_log.md`'s "Data & storage" section and the spec's own §4.6/§8 correction notes
- [x] `prices` table (`infra/postgres/init.sql`) — append-only in spirit (no deletion path exists), `(symbol, date)` primary key makes a same-day re-run idempotent (upsert, not insert-only) rather than erroring or duplicating on retry
- [x] `daily_symbol_features` dbt model (`services/daily-batch/dbt/models/daily_symbol_features.sql`) — materialized as a table, date grain is a real `UNION` of `prices` dates and article-activity dates (via `article_symbols`), verified live: a test article inserted on a date with no matching `prices` row produced a real row with `article_count=1`, `avg_ingestion_lag_seconds` correctly computed, and null price columns — exactly the spec'd non-join behavior, not gated on a price existing. `price_change_pct` computed via a real dbt `LAG()` window function, verified against 5 real trading days of live-fetched AAPL data. Two dbt schema tests (not-null) plus one singular composite-uniqueness test on `(symbol, date)`, all passing live
- [x] Complex-SQL stats queries (`services/query-api/infrastructure/stats_queries.py`) — three real window-function queries against `daily_symbol_features`, verified live against real Postgres: `rolling_article_volume` (`AVG() OVER (... ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`), `ingestion_lag_stats` (`PERCENTILE_CONT` for p50/p95), `price_deltas` (reads the dbt-computed day-over-day `LAG()` column). Built in query-api (not daily-batch) since it's a read path the stats UI will call — wiring an actual `/stats` HTTP endpoint around these is milestone 6's job (`docs/milestone.md` §6), this milestone's scope was the SQL itself existing and being demonstrably correct

## 6. UI — done
Query panel, digest view, live ingestion feed, stats.

- [x] Streamlit chat interface (`st.chat_message`/`st.chat_input`/`st.write_stream`) — already built in milestone 1 as the pipeline's stand-in UI; carried forward into `views/query_panel.py`
- [x] Query API's endpoint is a real streaming `StreamingResponse`, not buffered JSON — already true since milestone 1; also fixed the "Known follow-up from milestone 2": `/query` now derives `symbols` from the caller's real watchlist (JWT `sub` → `watchlist` lookup) instead of a client-supplied request field, verified live end-to-end
- [x] Watchlist management view (add/remove, inline validation errors) — `application/watchlist_service.py` + `infrastructure/finnhub_lookup.py` (exact-match validation, rejects Finnhub's fuzzy cross-exchange results like `AAPL.TO` for a plain `AAPL` query) + `infrastructure/postgres_watchlist_repo.py` (idempotent add via `ON CONFLICT DO UPDATE`) + `presentation/watchlist_api.py`. Verified live: real `POST /watchlist` with `AAPL` succeeds, a garbage symbol gets a real `422` from Finnhub's actual `/search` endpoint, `GET /watchlist` reflects it, `views/watchlist.py` surfaces the 422 detail inline via `st.error`
- [x] Live ingestion feed — `infrastructure/feed_queries.py` (real Postgres join across `articles`/`article_symbols`, scoped to watched symbols, most recent `ingested_at` first) + `presentation/feed_api.py` + `views/live_feed.py`. Verified live against real seeded articles: correctly excludes an unwatched symbol's article, correctly orders newest-first, correctly aggregates multiple watched symbols per article
- [x] Stats + cost-monitoring dashboard (one surface, not two) — `views/stats.py` renders milestone 5's window-function stats (`GET /stats`, wrapping `StatsQueries` + a new `overview_stats()` real-time query against `articles` directly, not the once-daily `daily_symbol_features`) plus an honest "not available in local dev" section for cloud cost monitoring (BigQuery `INFORMATION_SCHEMA.JOBS`, GCS/Pub-Sub usage APIs, §4.6) on the same page — real cloud wiring is milestone 7's job, not faked here. Verified live end-to-end: ran the real `daily-batch` job, then confirmed `/stats` returns real rolling-volume/ingestion-lag/price-delta figures matching milestone 5's own verification

**Bug found and fixed during this milestone's live verification, not before**: `app.py` was rewritten to use `st.navigation()` with pages under a directory named `pages/` (the natural name, matching `project-structure.md`'s original plan) — but Streamlit auto-discovers *any* folder literally named `pages/` as legacy multipage navigation **regardless of `st.navigation()`**, independently of and before the login gate ever runs. Confirmed live: the sidebar exposed "watchlist"/"live feed"/"stats"/"query panel" as directly clickable top-level pages that bypassed `app.py`'s `st.user.get("is_logged_in")` check entirely — a real authentication bypass, not a cosmetic bug. Fixed by renaming the directory to `views/` (user's explicit choice over adding a redundant auth check inside every page module) — Streamlit has no special handling for that name, so the login gate is the only path in again.

**Second bug found during the same verification pass**: after the `views/` fix, the UI still crashed on load with `TypeError: Couldn't parse file content!` from deep inside `google.protobuf`, while parsing `services/ui/auth/v1/auth_pb2.py`'s serialized file descriptor. Root cause: that generated file's descriptor bytes had a mismatched length-prefix byte for the `go_package` option string (`Z \x20` instead of the correct `Z$`, i.e. one byte short of the string's real length) — a latent corruption from whatever `protoc`/`grpc_tools` version generated it originally, which older/more lenient protobuf runtime versions apparently tolerated but the currently-pinned `protobuf==7.36.2` rejects outright. Fixed by regenerating the stub fresh from `services/auth/proto/auth/v1/auth.proto` with the current toolchain (`grpc_tools.protoc` from this project's own `services/ui` venv) — a 2-line diff in the generated file, both fixing the exact length-prefix mismatch. Caught only by actually loading the page in a browser after the `views/` rename, not by any prior review of the generated file (nobody reads generated protobuf byte literals by eye).

**Third bug, found only after being explicitly asked to double-check rather than during the original verification pass**: `GET /stats` returned a raw `500 Internal Server Error` (`psycopg.errors.UndefinedTable`) whenever `daily_symbol_features` doesn't exist yet — true for any fresh deployment before the daily-batch job has run once, and genuinely the state of the running stack at the time this was found. The original milestone 6 verification only ever exercised `/stats` *after* manually running the daily-batch job first, so this path was never actually hit live, despite already being flagged as a "known seam" in `decision_log_claude.md` — writing the gap down was not the same as fixing it, and claiming the milestone was "done and good" without re-checking was premature. Reproduced with a real `curl` against the running container (`500`, confirmed via `docker compose logs`), then fixed test-first: `tests/integration/test_stats_queries_missing_table.py` reproduces the crash, `StatsQueries` now checks `inspect(engine).has_table(...)` and returns empty/zeroed results per method instead of raising. Rebuilt the container, re-ran the exact same live `curl` with the table still genuinely absent, got a real `200` with zeroed stats. This is the standard the "verify against real infra" principle is actually supposed to meet — a passing test suite plus one earlier manual click-through wasn't enough on its own.

**Fourth bug, reported directly by the user in production, not found by any check run here**: `st.navigation(build_pages())` crashed with `StreamlitAPIException: Multiple Pages specified with URL pathname render` — every one of the four `views/*.py` modules names its entry function `render`, and `st.Page()` infers a URL pathname from the callable's own `__name__` when `url_path` isn't given explicitly, so all four collided on the literal string `"render"`. This was never caught in this session's own verification because that verification never got past the login screen — completing a real Google OAuth sign-in is out of bounds here, and `st.navigation()` only ever executes *after* successful login (the earlier `st.stop()` fires first for an unauthenticated session), so the exact line that crashed was structurally unreachable from anywhere this session could click. **This is a real gap in what "verified live" can mean for this specific service**, not a process failure to fix going forward — accepted here as an honest limit, not glossed over. Fixed by giving every `st.Page()` call an explicit, distinct `url_path`. To make this independently verifiable without needing a real login, `app.py`'s page-list construction was extracted into `views/navigation.py`'s `build_pages()`, callable and testable on its own. Confirmed two things directly, not by assumption: (1) `st.navigation()`'s pathname-collision check only fires inside a real Streamlit script-run context — a bare `python` script constructing the exact same buggy call does **not** raise, so a plain unit test would have given false confidence; (2) `streamlit.testing.v1.AppTest` does provide a real context and reproduces the *exact* reported error message byte-for-byte against the pre-fix code, then passes clean against the fix — `services/ui/tests/test_navigation.py`.

## 7. Cloud migration
Move queue, storage, and processing to GCP (Pub/Sub, GCS, Cloud Run, BigQuery).

- [ ] Terraform: Cloud Run (5 services + 1 job), Pub/Sub (push, not pull), GCS, BigQuery, Secret Manager, Cloud Scheduler
- [ ] IAM lockdown — `roles/run.invoker` matrix (`api-spec.md`'s per-service auth notes); only UI is `--allow-unauthenticated`
- [ ] Workload Identity Federation for CI/CD, scoped to `main`
- [ ] All 6 deployables live on GCP

## 8. Testing & CI/CD
pytest suite, GitHub Actions CI on all branches, `dev`/`main` branch split, Terraform for all GCP resources, CD gated to `main`.

- [ ] pytest, written before implementation, for: dedup key tiers, overflow-assignment ranking, cadence-scaling formula, symbol validation, JWT expiry/logout
- [ ] Go tests for Auth and Poller domain logic (same TDD discipline, Go-idiomatic structure)
- [ ] dbt schema tests (not-null, uniqueness) on `daily_symbol_features`
- [ ] GitHub Actions CI — tests + lint on every branch/PR
- [ ] GitHub Actions CD — gated to `main`, `terraform plan` on PR / `apply` on merge
- [ ] `dev`/`main` branch protection configured

## 9. Polish
Data quality checks, ingestion logging, cost-monitoring dashboard, README with architecture diagram.

- [ ] Data quality validation (non-empty text, valid symbol, no duplicate ingestion)
- [ ] `structlog` logging wired (console locally, JSON on Cloud Run)
- [ ] LLM spend ceiling set on the provider account + honest "cap reached" message path
- [ ] README — architecture diagram, data lineage notes, setup instructions

---

## Known gaps carried forward (not blockers, not forgotten)

- [ ] Symbol validation only covers Finnhub's coverage, not Marketaux's (§4.1)
- [ ] No poller liveness/health monitoring — silent-failure detection (§11, "Acknowledged gaps")
- [ ] No partial-failure/retry/dead-letter semantics across the pipeline (§11, "Acknowledged gaps")
- [ ] Overflow-boundary thrashing (no hysteresis) — accepted, not fixed (§4.2)

## v2 — not tracked here (§12)

Sentiment scoring, pattern detection, LLM tool-routing, twice-daily batch, historical backfill, JWT refresh flow. Fully designed, deliberately out of this milestone list until v1 ships — see `decision_log.md`'s "Deferred to v2" section for the one-line summaries.
