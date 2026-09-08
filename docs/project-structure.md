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
│   │   │   ├── api.py             # FastAPI app, wires /pubsub/push and the ingest_api router
│   │   │   └── ingest_api.py      # POST /articles/ingest — direct synchronous call into ProcessArticleUseCase, used by query-api's watchlist-add backfill (api-spec.md, decision_log.md — deliberately not routed through Pub/Sub)
│   │   ├── scripts/
│   │   │   └── seed_static_articles.py  # milestone 1 stand-in for the real poller (local/demo seeding)
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── query-api/                 # Python — lighter Clean Architecture (thin in v1, §8)
│   │   ├── domain/
│   │   │   ├── retrieval.py       # RetrievedChunk entity
│   │   │   ├── stats.py           # RollingVolumePoint/PriceDelta/OverviewStats entities (§4.6, milestones 5-6) —
│   │   │   │                      # IngestionLagStats deleted (unused three-figure avg/p50/p95 block, user's call,
│   │   │   │                      # decision_log.md), replaced by StatsQueries.total_ingestion()'s (7d, 30d) tuple.
│   │   │   │                      # RollingVolumePoint carries both rolling_avg_7d and rolling_avg_30d per point
│   │   │   │                      # (computed together in one query) — the per-symbol 7d|30d toggle needs both on
│   │   │   │                      # hand at once, not just whichever window was last requested
│   │   │   ├── watchlist.py       # WatchlistEntry entity (§4.1, milestone 6)
│   │   │   ├── feed.py            # FeedItem entity (§4.5, milestone 6) — includes canonical_url (nullable, user request)
│   │   │   └── backfill.py        # BackfillResult, SymbolBackfillResult, MultiSymbolBackfillResult entities — news backfill on watchlist-add, new v1 feature (decision_log.md)
│   │   ├── application/
│   │   │   ├── query_service.py   # retrieval + LLM call/streaming (§4.4); grows into full layering in v2 once tool-routing lands (§12.3)
│   │   │   ├── watchlist_service.py # add/list/remove, Finnhub validation before persisting (§4.1, milestone 6);
│   │   │   │                      # optionally triggers a BackfillService (news) and a JobTrigger (price/feature-store,
│   │   │   │                      # new v1 feature mirroring the news mechanism, decision_log.md) on add — both optional
│   │   │   │                      # dependencies, same shape, so either can be omitted without breaking add_symbol
│   │   │   ├── backfill_service.py # backfill_on_add() (BACKFILL_WINDOW_DAYS=30) / load_more() (extends 30 more
│   │   │   │                      # days back, and runs an initial backfill instead of erroring if the symbol was
│   │   │   │                      # never backfilled — real bug found live, decision_log_claude.md) /
│   │   │   │                      # load_more_for_symbols() (loops load_more() over every given symbol) —
│   │   │   │                      # symbol-scoped progress, not per-user (decision_log.md). The window is fetched as
│   │   │   │                      # sequential <=FETCH_CHUNK_DAYS(=14)-day chunks, not one wide call — Finnhub's
│   │   │   │                      # company-news endpoint doesn't reliably serve a single 30-day request for a busy
│   │   │   │                      # symbol (real live-tested timeout). Each chunk's fetch is best-effort (a failed
│   │   │   │                      # chunk logs a warning and is skipped, not fatal) — Finnhub was found live to be
│   │   │   │                      # unreliable under repeated calls even at the smaller chunk size, so retrying
│   │   │   │                      # wouldn't fix it; the goal is "add-symbol never 500s over third-party flakiness,"
│   │   │   │                      # not guaranteed-complete news coverage (decision_log.md). Progress is only
│   │   │   │                      # recorded once at least one chunk genuinely reaches Finnhub — real bug found
│   │   │   │                      # live: recording it unconditionally let a symbol whose every chunk failed get
│   │   │   │                      # permanently marked "backfilled" with zero articles, silently blocking any later
│   │   │   │                      # retry (decision_log_claude.md)
│   │   │   └── feed_load_older_service.py # FeedLoadOlderService — combines paging (FeedQueries, cheap) and backfilling
│   │   │                          # (BackfillService, real Finnhub calls) into one action for the Live Feed's single
│   │   │                          # "Load older news" button (user request: merge the two separate buttons). Pages
│   │   │                          # first; only backfills if that's empty, retrying through empty windows up to
│   │   │                          # MAX_BACKFILL_ATTEMPTS=6 (~3 months, user's chosen cap) before returning
│   │   │                          # exhausted=True. Live-verified: a deliberately-too-far cursor ran the full 108s
│   │   │                          # loop and correctly reported exhausted rather than hanging (decision_log_claude.md)
│   │   ├── infrastructure/
│   │   │   ├── pgvector_search.py # PgVectorRetriever — ORDER BY fixed to rank by vector similarity, not article_id (decision_log_claude.md: a real correctness bug found while debugging a flaky test, retrieval was effectively unranked once more than top_k articles existed for a symbol)
│   │   │   ├── stats_queries.py   # real window-function SQL against daily_symbol_features (§4.6, milestone 5) —
│   │   │   │                      # no `days` param: rolling_article_volume/total_ingestion/price_deltas each fetch
│   │   │   │                      # a fixed 30-day window per symbol and compute both 7d and 30d figures in that same
│   │   │   │                      # query (two AVG() OVER windows, one SUM()+SUM() FILTER pair) — 3 queries per symbol
│   │   │   │                      # total regardless of window count, not 6, once the Stats page's toggle went
│   │   │   │                      # per-symbol and every symbol needs both windows on hand (decision_log_claude.md,
│   │   │   │                      # the user's own "100 symbols" scaling question). ingestion_lag_stats() deleted
│   │   │   │                      # outright (unused, decision_log.md), plus overview_stats() (real-time
│   │   │   │                      # articles-today/tickers-tracked against articles/article_symbols directly, milestone 6)
│   │   │   ├── feed_queries.py    # recent articles scoped to watched symbols, ORDER BY (published_at, id) DESC —
│   │   │   │                      # corrected from ingested_at DESC after user clarification, and gained real keyset
│   │   │   │                      # pagination (before/before_id cursor, id as tiebreak for same-published_at rows) —
│   │   │   │                      # real bug found live: a fixed limit=50 made backfilled older articles structurally
│   │   │   │                      # unreachable regardless of how many times "load more" ran (§4.5, milestone 6, decision_log_claude.md).
│   │   │   │                      # First page only (no cursor) also takes an optional per_symbol_limit — guarantees
│   │   │   │                      # every watched symbol at least that many of its own recent articles via
│   │   │   │                      # ROW_NUMBER() PARTITION BY symbol, merged and re-sorted — real bug found live: a
│   │   │   │                      # high-volume symbol crowded a newly-added quieter symbol almost entirely out of the
│   │   │   │                      # feed even though its articles were real and present (decision_log_claude.md)
│   │   │   ├── finnhub_lookup.py  # FinnhubSymbolLookup — exact-match validation against /search, rejecting fuzzy cross-exchange matches (§4.1, milestone 6)
│   │   │   ├── finnhub_news_client.py # FinnhubNewsClient — Python port of poller's Go CompanyNews, used for on-demand backfill (not the continuous poll cycle)
│   │   │   ├── processing_ingest_client.py # calls processing's POST /articles/ingest directly — no Pub/Sub envelope (decision_log.md)
│   │   │   ├── postgres_watchlist_repo.py # idempotent add (ON CONFLICT DO UPDATE), scoped list/remove (milestone 6)
│   │   │   ├── postgres_backfill_repo.py # symbol_backfill_progress upsert/read
│   │   │   ├── system_clock.py    # SystemClock — real date.today(), injected so BackfillService is deterministically testable
│   │   │   ├── local_docker_job_trigger.py # LocalDockerJobTrigger — local-dev-only JobTrigger: shells out to
│   │   │   │                      # `docker compose run --rm daily-batch --symbol <X>` via a Docker-socket mount
│   │   │   │                      # (structurally absent from the cloud image; CloudRunJobTrigger, calling the real
│   │   │   │                      # GCP Cloud Run Jobs API, is deferred to the milestone 7 cloud migration itself —
│   │   │   │                      # same "don't write untestable cloud-only code early" precedent as the BigQuery gap,
│   │   │   │                      # decision_log.md). Selected only when COMPOSE_PROJECT_NAME is set (settings.py)
│   │   │   ├── llm_client.py      # streaming LLM call + spend-ceiling handling (§4.4)
│   │   │   ├── stub_llm.py        # StubLLMClient — zero-cost local/demo fallback when ANTHROPIC_API_KEY isn't set (decision_log_claude.md)
│   │   │   ├── jwt_verify.py      # local JWT verification, no call back to Auth (§6)
│   │   │   ├── settings.py        # env/config loading
│   │   │   └── logging.py         # structlog wiring
│   │   ├── presentation/
│   │   │   ├── api.py             # FastAPI app — wires all routers below plus /health
│   │   │   ├── query_api.py       # /query — symbols now derived from the caller's watchlist, not the request body (milestone 6, api-spec.md)
│   │   │   ├── watchlist_api.py   # GET/POST /watchlist, DELETE /watchlist/{symbol} (milestone 6) — backfill-more lives on feed_api.py instead, see below
│   │   │   ├── feed_api.py        # GET /feed (milestone 6, pagination + first-page-only per-symbol quota via
│   │   │   │                      # FIRST_PAGE_PER_SYMBOL_LIMIT=10), POST /feed/backfill-more (per-symbol backfill
│   │   │   │                      # primitive, moved here from watchlist_api.py per user request), and
│   │   │   │                      # POST /feed/load-older (FeedLoadOlderService — combines the two into one action
│   │   │   │                      # for the UI's single button, user request)
│   │   │   ├── stats_api.py       # GET /stats — overview + per-symbol breakdown (milestone 6). No query param: each
│   │   │   │                      # symbol's response nests window_7d/window_30d, both always present, so the UI's
│   │   │   │                      # per-symbol toggle (each watched symbol independent of the others, corrected after
│   │   │   │                      # a page-wide-toggle first attempt, decision_log.md) switches with no refetch
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
│   │   │   ├── formatting.py      # format_timestamp() — raw ISO datetimes were shown unformatted in the UI (user
│   │   │   │                      # report). Deliberately avoids strftime's %-d/%-I (no-leading-zero) directives —
│   │   │   │                      # confirmed they raise ValueError on Windows even though the deployed container is
│   │   │   │                      # Linux, where they'd have worked; written portably so local dev doesn't diverge
│   │   │   │                      # from prod (decision_log_claude.md)
│   │   │   ├── feed_filtering.py  # sort_and_filter_feed() — descending published_at sort made explicit (not just
│   │   │   │                      # relying on the backend's ORDER BY) + client-side watchlist-symbol filtering,
│   │   │   │                      # extracted so it's testable without a real login. Corrected from ingested_at to
│   │   │   │                      # published_at after user clarification — the two diverge for backfilled articles
│   │   │   │                      # (decision_log_claude.md)
│   │   │   ├── feed_pagination.py # next_page_cursor() — derives the before/before_id cursor from the oldest loaded
│   │   │   │                      # item, always against the unfiltered set (not what's currently symbol-filtered),
│   │   │   │                      # so paging while filtered doesn't lose track of other symbols' position
│   │   │   ├── query_panel.py     # chat interface (st.chat_message/st.chat_input/st.write_stream)
│   │   │   ├── watchlist.py       # watchlist management view (§4.5) — inline 422 error surfaced on rejection; no
│   │   │   │                      # longer has a backfill button (moved to live_feed.py, one button for all symbols
│   │   │   │                      # instead of per-symbol, user's explicit choice)
│   │   │   ├── live_feed.py       # live ingestion feed (§4.5) — watchlist-symbol multiselect filter (defaults to
│   │   │   │                      # all selected), feed list sorted descending by publish date, each article with an
│   │   │   │                      # "Open ↗" st.link_button (canonical_url, opens in a new tab — only rendered when
│   │   │   │                      # the article has a URL, since it's nullable). ONE "Load older news" button (user
│   │   │   │                      # request: combine pagination and the separate "Load 2 more weeks" backfill button
│   │   │   │                      # into a single action) calls POST /feed/load-older, which pages existing Postgres
│   │   │   │                      # data first and only reaches for a real Finnhub backfill if that's exhausted —
│   │   │   │                      # accumulates pages in st.session_state["feed_items"]
│   │   │   └── stats.py           # stats dashboard (§4.6) — window-function stats only; cloud cost monitoring
│   │   │                          # was cut from the design entirely, see decision_log.md (user's call: GCP's own
│   │   │                          # Billing console/budget alerts already do this better than an in-app copy would).
│   │   │                          # A 7d|30d st.radio toggle replaced the old fixed "7-day rolling article volume"
│   │   │                          # label, keyed per-symbol (session_state[f"stats_window_days_{symbol}"], each
│   │   │                          # watched symbol's toggle independent of every other's) — corrected from an
│   │   │                          # earlier page-wide-toggle version the user caught immediately ("7d 30d should be
│   │   │                          # per symbol", decision_log.md). Reads window_7d/window_30d straight from the
│   │   │                          # GET /stats response already in hand, no refetch on toggle
│   │   ├── tests/
│   │   │   ├── test_navigation.py # uses streamlit.testing.v1.AppTest, not a plain unit test — st.navigation()'s
│   │   │   │                      # pathname-collision check only runs inside a real Streamlit script-run context,
│   │   │   │                      # confirmed a bare `python` script does not raise even with the buggy code
│   │   │   ├── test_formatting.py # format_timestamp() unit tests, including the exact real timestamp the user
│   │   │   │                      # reported as unreadable
│   │   │   ├── test_feed_filtering.py # sort_and_filter_feed() unit tests — descending sort, no-selection-means-all,
│   │   │   │                      # multi-symbol article matching
│   │   │   └── test_feed_pagination.py # next_page_cursor() unit tests
│   │   ├── clients/
│   │   │   ├── auth_client.py     # gRPC call to Auth, explicit ID-token fetch (§6)
│   │   │   ├── query_api_client.py # HTTPS call to Query API, explicit ID-token fetch (§6)
│   │   │   ├── watchlist_client.py # GET/POST/DELETE /watchlist (milestone 6) — add uses a 60s timeout, not 10s
│   │   │   │                      # (real latency measured live: ~10s+ for a busy symbol's synchronous backfill).
│   │   │   │                      # No longer has backfill_more() — moved to feed_client.py
│   │   │   ├── feed_client.py     # GET /feed (milestone 6), with optional before/before_id cursor params for
│   │   │   │                      # pagination; backfill_more() → POST /feed/backfill-more (unused by the UI directly
│   │   │   │                      # now, kept for potential reuse); load_older() → POST /feed/load-older, the one
│   │   │   │                      # the UI actually calls (180s timeout — worst case runs the full backfill loop)
│   │   │   └── stats_client.py    # GET /stats (milestone 6)
│   │   ├── .streamlit/
│   │   │   └── secrets.toml.example  # template for real Google OAuth credentials (gitignored once filled in)
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   └── daily-batch/                # Python (Cloud Run Job) — needs the dbt runtime regardless of language preference (§6)
│       ├── main.py                # reads watched symbols (or just one, via --symbol), pulls OHLCV, upserts prices,
│       │                          # then shells out to real `dbt run` + `dbt test`. --symbol added for the on-add
│       │                          # trigger (decision_log.md) — same image/entrypoint serves both the scheduled full
│       │                          # sweep (no flag) and a single-symbol run, rather than two separate images
│       ├── prices/
│       │   ├── yahoo_client.py    # Yahoo Finance chart API client — corrected from Finnhub's candle endpoint mid-milestone-5 (decision_log.md: live 403, endpoint now Premium-gated)
│       │   ├── prices_repo.py     # upsert into `prices`, idempotent on (symbol, date)
│       │   ├── run_daily_batch.py # orchestration: per-symbol fetch+upsert, isolates one symbol's failure from the
│       │   │                      # rest; takes a `range_` param (default "5d") passed through to fetch_daily_bars()
│       │   ├── symbol_resolution.py # resolve_symbols(cli_symbol, watched_symbols) — [cli_symbol] if given, else the
│       │   │                      # full watched list. Trusts a given symbol as-is rather than checking it against the
│       │   │                      # current watchlist snapshot (the on-add trigger fires before a fresh read is guaranteed
│       │   │                      # to see it yet, decision_log.md). resolve_range(cli_symbol) — "1mo" for a single
│       │   │                      # on-add symbol (a fresh symbol needs 30 real days for the Stats page's 30d view
│       │   │                      # immediately, user request), "5d" for the scheduled sweep, unchanged
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
│   ├── postgres/init.sql            # schema, applied by docker-compose on first Postgres start (built) — includes `prices` (milestone 5, local BigQuery stand-in) and `symbol_backfill_progress` (news backfill feature)
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
├── docker-compose.yml               # local dev — all 6 services + Postgres, no cloud dependency (§10.1). query-api's
│                                     # service mounts the Docker socket + this repo root (read-only, at /workspace) —
│                                     # local-only, for LocalDockerJobTrigger (decision_log.md); never present in the
│                                     # cloud deployment
├── .github/workflows/
│   ├── ci.yml                       # runs on every branch/PR — tests + lint (§10.3)
│   └── cd.yml                       # gated to main only — terraform plan on PR, apply on merge (§10.4)
└── README.md                        # architecture diagram, lineage notes, setup instructions (§5)
```

**Branching**: `dev` (local only, never deploys) → `main` (always what's live on GCP), per `decision_log.md` — no long-lived `v1`/`v2` branches, milestones tracked via `milestone.md` and tags instead.
