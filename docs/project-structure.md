# Project structure

Monorepo, one repo covering all 6 deployables (§6) — simplest for a solo build, and Terraform/CI already assume one repo (§10). Reflects the microservices-from-the-start decision (no monolith phase, `decision_log.md`) and the per-language architecture split (Clean Architecture for Python, Go-idiomatic package-per-feature for Go — `decision_log.md`).

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
│   │   │       ├── processing_client.go # publishes to Processing's /pubsub/push directly — stand-in for the real queue until milestone 4
│   │   │       ├── cycle.go             # RunCycle: one poll cycle's orchestration (read watchlist -> assign sources -> poll -> publish)
│   │   │       └── http.go              # the /trigger handler Cloud Scheduler calls
│   │   ├── tests/integration/     # live-Postgres/live-Processing checks (docker compose up postgres processing)
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
│   │   │   └── retrieval.py       # RetrievedChunk entity; symbol-validation domain logic (§4.1) not yet built — watchlist endpoint is deferred (milestone.md)
│   │   ├── application/
│   │   │   └── query_service.py   # retrieval + LLM call/streaming (§4.4); grows into full layering in v2 once tool-routing lands (§12.3). No watchlist_service.py yet — watchlist endpoint deferred (milestone.md's "Known follow-up")
│   │   ├── infrastructure/
│   │   │   ├── pgvector_search.py
│   │   │   ├── llm_client.py      # streaming LLM call + spend-ceiling handling (§4.4)
│   │   │   ├── stub_llm.py        # StubLLMClient — zero-cost local/demo fallback when ANTHROPIC_API_KEY isn't set (decision_log_claude.md)
│   │   │   ├── jwt_verify.py      # local JWT verification, no call back to Auth (§6)
│   │   │   ├── settings.py        # env/config loading
│   │   │   └── logging.py         # structlog wiring
│   │   │                          # No postgres_repo.py / finnhub_lookup.py yet — both belong to the not-yet-built watchlist endpoint
│   │   ├── presentation/
│   │   │   ├── api.py             # FastAPI app — /health, /query only; /watchlist not yet built (api-spec.md, milestone.md)
│   │   │   └── auth_dependency.py # require_auth() — Bearer-token FastAPI dependency wrapping jwt_verify
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── ui/                        # Python (Streamlit) — no Clean Architecture, it's a thin presentation shell
│   │   ├── app.py                 # st.login(), chat interface (st.chat_message/st.chat_input/st.write_stream)
│   │   ├── auth/v1/               # generated grpc stubs (auth_pb2.py, auth_pb2_grpc.py) from auth's .proto — MUST live
│   │   │                          # here at the import root, not nested under clients/ (decision_log_claude.md: the
│   │   │                          # generated _grpc.py always does `from auth.v1 import auth_pb2`, an absolute import
│   │   │                          # matching the .proto's package path regardless of --python_out)
│   │   ├── pages/
│   │   │   ├── watchlist.py       # watchlist management view (§4.5)
│   │   │   ├── live_feed.py
│   │   │   └── stats.py           # stats + cost-monitoring dashboard, one surface not two (§4.6)
│   │   ├── clients/
│   │   │   ├── auth_client.py     # gRPC call to Auth, explicit ID-token fetch (§6)
│   │   │   └── query_api_client.py # HTTPS call to Query API, explicit ID-token fetch (§6)
│   │   ├── .streamlit/
│   │   │   └── secrets.toml.example  # template for real Google OAuth credentials (gitignored once filled in)
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   └── daily-batch/                # Python (Cloud Run Job) — needs the dbt runtime regardless of language preference (§6)
│       ├── main.py                # pulls OHLCV, finalizes prices, then shells out to `dbt run`
│       ├── dbt/
│       │   ├── models/
│       │   │   └── daily_symbol_features.sql   # materialized: table (§4.6)
│       │   └── dbt_project.yml
│       ├── pyproject.toml
│       └── Dockerfile
│
├── infra/                          # Terraform (§10.5)
│   ├── main.tf
│   ├── cloud_run.tf                 # 5 services + 1 job, request-only CPU / min-instances=0 defaults left alone (§8)
│   ├── iam.tf                       # per-service roles/run.invoker bindings (§6, §10.5) — the ingress matrix
│   ├── secrets.tf                   # secret *containers* + IAM only, never values (§10.5)
│   ├── scheduler.tf                 # poller (every minute) + daily batch (once daily) triggers
│   ├── pubsub.tf                    # topic + push subscription (not pull, §6)
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
