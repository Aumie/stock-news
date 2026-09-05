# Milestones — progress tracking

Tracks progress against `stock-news-digest-requirements.md` §9. Update checkboxes as work lands — this is the "where are we" doc, not a place to re-explain decisions (that's `decision_log.md`).

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

**Current milestone:** 2 (Auth) — next up

---

## 1. Core RAG loop — done
Static ingestion of a fixed symbol list (unstructured news) → embed → query, working end to end.

- [x] Processing service skeleton (domain/dedup logic, chunking, embeddings)
- [x] Query API skeleton (retrieval + LLM call, no auth yet)
- [x] Static/hardcoded symbol list ingestion (stand-in for the real poller)
- [x] Local pgvector via docker-compose
- [x] End-to-end check: ingest a few articles → embed → ask a question → get a grounded answer (LLM stubbed by default for local/cost-sensitive dev — see `decision_log_claude.md`; retrieval and grounding verified for real against live Postgres/pgvector)

## 2. Auth
Google OAuth2 login, user + watchlist tables.

- [ ] Auth service (Go + gRPC) — `ExchangeIdentity` RPC, JWT issuance (`api-spec.md`)
- [ ] `users` + `watchlist` tables (`er-diagram.md`)
- [ ] Streamlit `st.login()` integration
- [ ] JWT verification in Query API (local, no call-back to Auth)

## 3. Dynamic symbol coverage
Poller re-reads distinct watched symbols each cycle and adjusts its polling set automatically.

- [ ] Poller service (Go) — Finnhub client, overflow-assignment rule, cadence-scaling formula
- [ ] Marketaux client (overflow lane)
- [ ] **Live check before building overflow logic further**: Marketaux's per-request symbol limit and reset-boundary behavior (§4.2 — flagged as the single highest-risk unverified assumption in the whole spec)
- [ ] Cloud Scheduler trigger design validated locally (simple interval loop stands in for it in docker-compose)

## 4. Microservices split — MVP checkpoint
Separate poller, processing, and query services communicating via queue.

- [ ] Pub/Sub (or local equivalent) wiring, poller → processing
- [ ] Three-tier dedup implemented (`content_hash` on `published_at`, `canonical_url`, fuzzy headline) + DB constraints
- [ ] Cross-source dedup actually exercised (same story via Finnhub and Marketaux)
- [ ] **MVP checkpoint reached** — this is the honest "few weeks" target (§2); if time runs out anywhere, this is where it's still fair to call it done

## 5. Structured pipeline & feature store
Cloud Scheduler + Cloud Run batch job pulls daily closing price/volume; dbt model into `daily_symbol_features`; complex-SQL stats queries.

- [ ] Daily batch job (Python + dbt), Cloud Run Job shape
- [ ] `prices` table (append-only, no rolling deletion)
- [ ] `daily_symbol_features` dbt model — materialized as a table, date grain is the union of `prices` dates and article-activity dates
- [ ] Complex-SQL stats queries (window functions — rolling volume, ingestion-lag percentiles, day-over-day deltas)

## 6. UI
Query panel, digest view, live ingestion feed, stats.

- [ ] Streamlit chat interface (`st.chat_message`/`st.chat_input`/`st.write_stream`)
- [ ] Query API's endpoint is a real streaming `StreamingResponse`, not buffered JSON
- [ ] Watchlist management view (add/remove, inline validation errors)
- [ ] Live ingestion feed
- [ ] Stats + cost-monitoring dashboard (one surface, not two)

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
