# Project structure

Monorepo, one repo covering all 6 deployables (§6) — simplest for a solo build, and Terraform/CI already assume one repo (§10). Reflects the microservices-from-the-start decision (no monolith phase, `decision_log.md`) and the per-language architecture split (Clean Architecture for Python, Go-idiomatic package-per-feature for Go — `decision_log.md`). Local dev also runs the real GCP Pub/Sub emulator (`docker-compose.yml`, `infra/pubsub-emulator/`) ahead of the milestone 7 cloud migration — no extra bridging service needed, since the emulator supports genuine push subscriptions and calls Processing's `/pubsub/push` directly (decision_log.md's "Local queue, corrected" entry). An earlier Redis Streams + relay design was tried and fully replaced; nothing from it remains in this repo.

```
.
├── services/
│   ├── auth/                      # Go, gRPC — package-per-feature, no layered folders (decision_log.md)
│   │   ├── cmd/server/
│   │   │   └── main.go            # explicit wiring — constructs the Postgres repo + JWT signer, no DI container
│   │   ├── internal/
│   │   │   └── auth/
│   │   │       ├── auth.go        # entity (User) + business rule (identity exchange, JWT expiry) — no framework/DB imports
│   │   │       ├── service.go     # ExchangeIdentity use case; defines the Repository/TokenSigner interfaces it needs, right here
│   │   │       ├── postgres.go    # Repository implementation
│   │   │       ├── jwt.go         # TokenSigner implementation
│   │   │       └── grpc.go        # gRPC handler — translates proto <-> service calls, the only place proto types appear
│   │   ├── proto/auth/v1/auth.proto   # matches api-spec.md
│   │   ├── go.mod
│   │   └── Dockerfile
│   │
│   ├── poller/                    # Go — same package-per-feature idiom as auth
│   │   ├── cmd/server/main.go
│   │   ├── internal/
│   │   │   └── poller/
│   │   │       ├── overflow.go          # overflow-assignment ranking rule (§4.2) — pure, no I/O, TDD target
│   │   │       ├── cadence.go           # cadence-scaling formula (§4.2) — pure, TDD target
│   │   │       ├── finnhub.go           # Finnhub client — no dedup_key.go: dedup itself lives in Processing (Python), poller only tags symbol+timestamp on publish
│   │   │       ├── marketaux.go         # Marketaux client (overflow lane) — batched at 50 symbols/call, verified live (milestone.md §3)
│   │   │       ├── postgres.go          # watchlist read (aggregates watcher count + earliest added_at per symbol)
│   │   │       ├── pubsub_publisher.go  # PubSubPublisher (cloud.google.com/go/pubsub/v2) — the real Publisher used in main.go; PUBSUB_EMULATOR_HOST redirects it locally, no code branching (decision_log_claude.md)
│   │   │       ├── processing_client.go # publishes to Processing's /pubsub/push directly — milestone 1-3's stand-in, kept (tested, unused in main.go) as a reference for the pre-queue approach
│   │   │       ├── cycle.go             # RunCycle: one poll cycle's orchestration (read watchlist -> assign sources -> poll -> publish)
│   │   │       └── http.go              # the /trigger handler Cloud Scheduler calls
│   │   ├── tests/integration/     # live-Postgres/live-Pub-Sub-emulator/live-Processing checks (docker compose up postgres pubsub-emulator processing)
│   │   ├── go.mod
│   │   └── Dockerfile
│   │
│   ├── processing/                # Python — full Clean Architecture layering (real domain logic, §8)
│   │   ├── domain/
│   │   │   ├── article.py         # entities — Article, ArticleSymbol
│   │   │   ├── dedup.py           # the three-tier dedup priority (§4.3) — pure, no DB/HTTP, the main TDD target here
│   │   │   └── repository.py      # Protocol interfaces (ArticleRepository, UnitOfWork, Embedder, Chunker, ...) — defined in domain/, implemented in infrastructure/
│   │   ├── application/
│   │   │   └── process_article.py # use case: consume -> dedup -> chunk -> embed -> persist, orchestrates domain + infra interfaces
│   │   ├── infrastructure/
│   │   │   ├── postgres_repo.py   # implements ArticleRepository — atomic ON CONFLICT ... DO UPDATE ... RETURNING upserts (decision_log_claude.md)
│   │   │   ├── unit_of_work.py    # PostgresUnitOfWork — one transaction spanning insert + symbol-link + embedding-write (decision_log_claude.md)
│   │   │   ├── dedup_precheck.py  # read-only pre-check to skip embedding an already-known article before opening a transaction
│   │   │   ├── embedding_writer.py # implements EmbeddingWriter — ON CONFLICT (article_id, chunk_index) DO NOTHING
│   │   │   ├── embeddings.py      # sentence-transformers (all-MiniLM-L6-v2) adapter
│   │   │   ├── chunking.py        # text chunker
│   │   │   ├── pubsub.py          # push-subscription payload parsing
│   │   │   ├── settings.py        # env/config loading
│   │   │   └── logging.py         # structlog wiring
│   │   ├── presentation/
│   │   │   └── api.py             # FastAPI app, POST /pubsub/push (api-spec.md)
│   │   ├── scripts/
│   │   │   └── seed_static_articles.py  # milestone 1 stand-in for the real poller (local/demo seeding)
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── query-api/                 # Python — lighter Clean Architecture (thin in v1, §8)
│   │   ├── domain/
│   │   │   ├── retrieval.py       # RetrievedChunk entity
│   │   │   ├── stats.py           # RollingVolumePoint/IngestionLagStats/PriceDelta/OverviewStats entities (§4.6, milestones 5-6)
│   │   │   ├── watchlist.py       # WatchlistEntry entity (§4.1, milestone 6)
│   │   │   └── feed.py            # FeedItem entity (§4.5, milestone 6)
│   │   ├── application/
│   │   │   ├── query_service.py   # retrieval + LLM call/streaming (§4.4); grows into full layering in v2 once tool-routing lands (§12.3)
│   │   │   └── watchlist_service.py # add/list/remove, Finnhub validation before persisting (§4.1, milestone 6)
│   │   ├── infrastructure/
│   │   │   ├── pgvector_search.py
│   │   │   ├── stats_queries.py   # real window-function SQL against daily_symbol_features (§4.6, milestone 5) — rolling 7-day volume, ingestion-lag percentiles, day-over-day price deltas, plus overview_stats() (real-time articles-today/tickers-tracked against articles/article_symbols directly, milestone 6)
│   │   │   ├── feed_queries.py    # recent articles scoped to watched symbols, most recent first (§4.5, milestone 6)
│   │   │   ├── finnhub_lookup.py  # FinnhubSymbolLookup — exact-match validation against /search, rejecting fuzzy cross-exchange matches (§4.1, milestone 6)
│   │   │   ├── postgres_watchlist_repo.py # idempotent add (ON CONFLICT DO UPDATE), scoped list/remove (milestone 6)
│   │   │   ├── llm_client.py      # streaming LLM call + spend-ceiling handling (§4.4)
│   │   │   ├── stub_llm.py        # StubLLMClient — zero-cost local/demo fallback when ANTHROPIC_API_KEY isn't set (decision_log_claude.md)
│   │   │   ├── jwt_verify.py      # local JWT verification, no call back to Auth (§6)
│   │   │   ├── settings.py        # env/config loading
│   │   │   └── logging.py         # structlog wiring
│   │   ├── presentation/
│   │   │   ├── api.py             # FastAPI app — wires all routers below plus /health
│   │   │   ├── query_api.py       # /query — symbols now derived from the caller's watchlist, not the request body (milestone 6, api-spec.md)
│   │   │   ├── watchlist_api.py   # GET/POST /watchlist, DELETE /watchlist/{symbol} (milestone 6)
│   │   │   ├── feed_api.py        # GET /feed (milestone 6)
│   │   │   ├── stats_api.py       # GET /stats — overview + per-symbol breakdown (milestone 6)
│   │   │   └── auth_dependency.py # require_auth() — Bearer-token FastAPI dependency wrapping jwt_verify
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── ui/                        # Python (Streamlit) — no Clean Architecture, it's a thin presentation shell
│   │   ├── app.py                 # st.login() gate, then st.navigation(build_pages()) — page construction lives in
│   │   │                          # views/navigation.py so it's testable independent of the login gate (see tests/)
│   │   ├── auth/v1/               # generated grpc stubs (auth_pb2.py, auth_pb2_grpc.py) from auth's .proto — MUST live
│   │   │                          # here at the import root, not nested under clients/ (decision_log_claude.md: the
│   │   │                          # generated _grpc.py always does `from auth.v1 import auth_pb2`, an absolute import
│   │   │                          # matching the .proto's package path regardless of --python_out). Regenerated in
│   │   │                          # milestone 6 after a stale descriptor (wrong length-prefix byte from an older
│   │   │                          # protoc run) failed to parse under the current pinned protobuf version.
│   │   ├── views/                 # NOT named `pages/` — Streamlit auto-discovers any folder literally named `pages/`
│   │   │   │                      # as legacy multipage navigation regardless of st.navigation(), which bypassed
│   │   │   │                      # app.py's login gate entirely (confirmed live, decision_log_claude.md). Each
│   │   │   │                      # module exposes a render() function app.py wires into st.Page().
│   │   │   ├── navigation.py      # build_pages() — every view's entry point is named `render`, so each st.Page()
│   │   │   │                      # needs an explicit, distinct url_path or they collide (confirmed live: a real
│   │   │   │                      # StreamlitAPIException in production, decision_log_claude.md). Extracted from
│   │   │   │                      # app.py so it's callable/testable without a real login (see tests/test_navigation.py)
│   │   │   ├── query_panel.py     # chat interface (st.chat_message/st.chat_input/st.write_stream)
│   │   │   ├── watchlist.py       # watchlist management view (§4.5) — inline 422 error surfaced on rejection
│   │   │   ├── live_feed.py       # live ingestion feed (§4.5)
│   │   │   └── stats.py           # stats + cost-monitoring dashboard, one surface not two (§4.6) — cost-monitoring
│   │   │                          # section is an explicit "not available locally" note, not faked data (real
│   │   │                          # BigQuery INFORMATION_SCHEMA.JOBS/GCS/Pub-Sub wiring is milestone 7's job)
│   │   ├── tests/
│   │   │   └── test_navigation.py # uses streamlit.testing.v1.AppTest, not a plain unit test — st.navigation()'s
│   │   │                          # pathname-collision check only runs inside a real Streamlit script-run context,
│   │   │                          # confirmed a bare `python` script does not raise even with the buggy code
│   │   ├── clients/
│   │   │   ├── auth_client.py     # gRPC call to Auth, explicit ID-token fetch (§6)
│   │   │   ├── query_api_client.py # HTTPS call to Query API, explicit ID-token fetch (§6)
│   │   │   ├── watchlist_client.py # GET/POST/DELETE /watchlist (milestone 6)
│   │   │   ├── feed_client.py     # GET /feed (milestone 6)
│   │   │   └── stats_client.py    # GET /stats (milestone 6)
│   │   ├── .streamlit/
│   │   │   └── secrets.toml.example  # template for real Google OAuth credentials (gitignored once filled in)
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   └── daily-batch/                # Python (Cloud Run Job) — needs the dbt runtime regardless of language preference (§6)
│       ├── main.py                # reads watched symbols, pulls OHLCV, upserts prices, then shells out to real `dbt run` + `dbt test`
│       ├── prices/
│       │   ├── yahoo_client.py    # Yahoo Finance chart API client — corrected from Finnhub's candle endpoint mid-milestone-5 (decision_log.md: live 403, endpoint now Premium-gated)
│       │   ├── prices_repo.py     # upsert into `prices`, idempotent on (symbol, date)
│       │   ├── run_daily_batch.py # orchestration: per-symbol fetch+upsert, isolates one symbol's failure from the rest
│       │   ├── settings.py        # env/config loading
│       │   └── logging.py         # structlog wiring
│       ├── dbt/
│       │   ├── models/
│       │   │   ├── daily_symbol_features.sql   # materialized: table (§4.6) — date grain is a real UNION of prices dates + article-activity dates
│       │   │   └── schema.yml     # not-null tests
│       │   ├── tests/
│       │   │   └── assert_no_duplicate_symbol_date.sql  # singular composite-uniqueness test (no dbt_utils dependency needed for just this)
│       │   ├── dbt_project.yml
│       │   └── profiles.yml       # postgres target locally (decision_log.md's BigQuery-stand-in entry) — credentials via env_var(), nothing hardcoded
│       ├── tests/                 # unit tests (fake Yahoo client/repo) + tests/integration/ (real Postgres, real live Yahoo Finance call)
│       ├── pyproject.toml
│       └── Dockerfile
│
├── infra/
│   ├── postgres/init.sql            # schema, applied by docker-compose on first Postgres start (built) — includes `prices` (milestone 5, local BigQuery stand-in)
│   ├── pubsub-emulator/config.json  # topic + push subscription config for the local emulator (built, decision_log.md)
│   │                                 # --- Terraform below is planned for milestone 7, not yet built ---
│   ├── main.tf
│   ├── cloud_run.tf                 # 5 services + 1 job, request-only CPU / min-instances=0 defaults left alone (§8)
│   ├── iam.tf                       # per-service roles/run.invoker bindings (§6, §10.5) — the ingress matrix
│   ├── secrets.tf                   # secret *containers* + IAM only, never values (§10.5)
│   ├── scheduler.tf                 # poller (every minute) + daily batch (once daily) triggers
│   ├── pubsub.tf                    # real GCP topic + push subscription (not pull, §6) — replaces the local emulator's config.json at cloud migration
│   └── workload_identity.tf         # WIF trust, scoped to main (§10.4)
│
├── docs/
│   ├── stock-news-digest-requirements.md   # the spec
│   ├── decision_log.md                     # the why, by topic — decisions the user made/directed
│   ├── decision_log_claude.md              # implementation-level judgment calls made while coding
│   ├── api-spec.md                         # this file's sibling
│   ├── er-diagram.md
│   ├── project-structure.md                # this file
│   └── milestone.md                        # progress tracking
│
├── docker-compose.yml               # local dev — all 6 services + Postgres, no cloud dependency (§10.1)
├── .github/workflows/
│   ├── ci.yml                       # runs on every branch/PR — tests + lint (§10.3)
│   └── cd.yml                       # gated to main only — terraform plan on PR, apply on merge (§10.4)
└── README.md                        # architecture diagram, lineage notes, setup instructions (§5)
```

**Branching**: `dev` (local only, never deploys) → `main` (always what's live on GCP), per `decision_log.md` — no long-lived `v1`/`v2` branches, milestones tracked via `milestone.md` and tags instead.
