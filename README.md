# py_wallet-snapshot-service

FastAPI microservice that creates and processes wallet snapshot jobs for `py_wallet`.
It reads active users and wallets from the shared PostgreSQL database, collects EVM
native and configured ERC-20 balances through RPC, includes manual wallet balances,
writes normalized snapshot rows back to PostgreSQL, and exposes operational metrics
for Prometheus.

Prometheus is used only for telemetry. Portfolio data is business data and must be
read from PostgreSQL by `py_wallet`.

```text
py_wallet backend -> snapshot-service internal API
snapshot-service  -> PostgreSQL + EVM RPC + price providers
Prometheus        -> /metrics
```

## Responsibilities

- Exposes health, metrics, debug, and internal snapshot job endpoints.
- Creates manual, scheduled, and retry jobs.
- Runs the FastAPI app, worker loop, and scheduler loop in one process.
- Claims pending jobs with PostgreSQL row locking via `FOR UPDATE SKIP LOCKED`.
- Reads `py_wallet`-owned tables: `users`, `wallet_groups`, `wallets`, `assets`, `manual_balances`.
- Owns snapshot tables: `snapshot_runs`, `wallet_snapshots`, `chain_snapshots`, `snapshot_balance_snapshots`.
- Collects EVM native and USDC-family balances for `mainnet`, `base`, `arbitrum`,
  `bnb`, and `linea`.
- Distinguishes native USDC, bridged `USDC.e`/`USDbC`, and Binance-Peg USDC.
- Validates RPC chain IDs at startup and supports comma-separated RPC failover with
  cooldown-based circuit breaking.
- Processes manual wallets without RPC calls.
- Uses CoinGecko for prices with local fallback prices for common symbols.
- Supports partial success at job, wallet, and chain level.

## Project Layout

```text
app/
  api/            FastAPI routers for health, metrics, debug, and internal jobs
  models/         SQLAlchemy models for external py_wallet tables and snapshot tables
  schemas/        Pydantic request/response schemas
  services/       job creation, wallet loading, collectors, prices, snapshot processing
  scheduler/      scheduled job producer loop
  worker/         pending job claim and processing loop
alembic/          snapshot-service migrations
docs/             local runbooks and service interaction notes
tests/            API, worker, scheduler, manual wallet, and partial success tests
```

## Local Python Setup

Requirements:

- Python 3.12+
- PostgreSQL database shared with `py_wallet`
- RPC URLs for full EVM processing

Install dependencies:

```bash
uv sync --frozen --extra dev
source .venv/bin/activate
cp .env.example .env
```

`uv.lock` is committed and is the dependency source of truth for local, CI,
and container environments. Run `uv lock --check` to verify that it still
matches `pyproject.toml`; intentionally update it with `uv lock`.

Set `DATABASE_URL` in `.env`, then run snapshot-service migrations:

```bash
alembic upgrade head
```

Start the service:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

For API-only smoke testing without background processing:

```env
SNAPSHOT_WORKER_ENABLED=false
SNAPSHOT_SCHEDULER_ENABLED=false
```

## Docker Setup

Build the local image:

```bash
docker build -t py_wallet_snapshot_service:dev .
```

Run with Docker Compose:

```bash
docker compose up -d
```

The compose file runs the image as `py-wallet-snapshot-service` on the external
Docker network `py_wallet_default` and publishes port `8001`.

When running inside Docker, `localhost` points to the snapshot-service container.
Use the PostgreSQL service name from the shared Docker network in `DATABASE_URL`,
for example:

```env
DATABASE_URL=postgresql+psycopg://wallet:wallet@postgres:5432/wallet
```

Run migrations from the container image:

```bash
docker compose run --rm snapshot-service alembic upgrade head
```

If `py_wallet` calls this service from the same Docker network, keep the container
name/DNS name stable:

```text
http://py-wallet-snapshot-service:8001
```

See `docs/service-interaction-and-local-runbook.md` for the full local integration
runbook with `py_wallet`.

## Configuration

Configuration is loaded from environment variables and `.env`.

Core variables:

- `APP_NAME`
- `ENVIRONMENT`
- `LOG_LEVEL`
- `DATABASE_URL`
- `INTERNAL_API_TOKEN`
- `SNAPSHOT_SERVICE_HOST`
- `SNAPSHOT_SERVICE_PORT`

`INTERNAL_API_TOKEN` is required in every environment. Generate it instead of
using the example placeholder:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In `staging` and `production`, startup rejects empty, known-placeholder, and
shorter-than-32-character tokens. Configure the same generated value in
`py_wallet` as `SNAPSHOT_INTERNAL_API_TOKEN`.

Background processing:

- `SNAPSHOT_WORKER_ENABLED`
- `SNAPSHOT_SCHEDULER_ENABLED`
- `SNAPSHOT_INTERVAL_SECONDS`
- `SNAPSHOT_WORKER_POLL_SECONDS`
- `SNAPSHOT_ENABLED_CHAINS`
- `MAX_RETRY_ATTEMPTS`
- `RETRY_BACKOFF_SECONDS`

Debug and external providers:

- `DEBUG_ENDPOINTS_ENABLED`
- `ETHEREUM_RPC_URL`
- `BASE_RPC_URL`
- `ARBITRUM_RPC_URL`
- `BNB_RPC_URL`
- `LINEA_RPC_URL`
- `CHAIN_TIMEOUT_SECONDS`
- `ETHEREUM_TIMEOUT_SECONDS`
- `RPC_COOLDOWN_SECONDS`
- `RPC_STARTUP_CHECK_ENABLED`
- `COINGECKO_BASE_URL`
- `PRICE_CACHE_TTL_SECONDS`

See `.env.example` for defaults.

Each `*_RPC_URL` accepts a comma-separated list ordered as primary, backup, and
emergency endpoint. Failed endpoints are removed from rotation for
`RPC_COOLDOWN_SECONDS`; startup checks verify that every endpoint reports the
expected chain ID.

For local mainnet-only debugging, set:

```env
SNAPSHOT_ENABLED_CHAINS=mainnet
```

The full EVM set is `mainnet,base,arbitrum,bnb,linea`.

## API

Health:

```bash
curl http://localhost:8001/health
```

Metrics:

```bash
curl http://localhost:8001/metrics
```

List debug jobs when `DEBUG_ENDPOINTS_ENABLED=true`:

```bash
curl "http://localhost:8001/debug/jobs?limit=20"
```

Get a debug job with wallet and chain details:

```bash
curl http://localhost:8001/debug/jobs/123
```

Debug-check native EVM balance using the same collector path as snapshot processing:

```bash
curl "http://localhost:8001/debug/evm-balance?chain=mainnet&address=0x74100A58eC575F7c9E127B464cAf4609e36ee0BB" \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}"
```

Create a snapshot job:

```bash
curl -X POST http://localhost:8001/internal/snapshot-jobs \
  -H 'Content-Type: application/json' \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  -d '{"user_id":1,"trigger_type":"manual","scope_type":"all"}'
```

Supported job scopes:

- `all`
- `group` with `group_id`
- `wallet` with `wallet_id`
- `failed_chains` for retry jobs

Retry failed chains from a parent job:

```bash
curl -X POST http://localhost:8001/internal/snapshot-jobs/123/retry-failed \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}"
```

Get job status for backend polling:

```bash
curl http://localhost:8001/internal/snapshot-jobs/123 \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}"
```

Internal job endpoints require `X-Internal-Token`.

## Worker And Scheduler

The scheduler creates `scheduled/all/pending` jobs for active users who have active
wallets. It skips users that already have a scheduled pending or running job.
Scheduler and worker tick failures are logged and retried on the next interval so a
temporary database or provider error cannot silently stop background processing.

The worker loop:

1. Updates pending/running job gauges.
2. Claims the oldest pending job.
3. Marks it `running`.
4. Loads active wallets for the job scope.
5. Collects balances for manual wallets or supported EVM chains.
6. Writes wallet, chain, and balance snapshots.
7. Marks the job `success`, `partial_success`, or `failed`.

Retry jobs store `parent_run_id`, use `scope_type=failed_chains`, and process only
failed chains from the parent job for matching wallets.

Missing RPC URLs are recorded as failed chain snapshots with
`error_type=missing_rpc_url`. Other wallets/chains can still complete, so the final
job status may be `partial_success`.

## Database And Migrations

`py_wallet` owns the user-facing domain tables. This service only maps the columns
it needs:

- `users(id, email, is_active)`
- `wallet_groups(id, user_id, name)`
- `wallets(id, user_id, group_id, label, address, chain_type, wallet_type, is_active)`
- `assets(id, symbol, name, contract_address, chain, decimals)`
- `manual_balances(wallet_id, asset_id, amount, price_usd)`

`py_wallet-snapshot-service` owns:

- `snapshot_runs`
- `wallet_snapshots`
- `chain_snapshots`
- `snapshot_balance_snapshots`

Alembic uses a dedicated version table:

```text
snapshot_service_alembic_version
```

This is intentional because `py_wallet` and `py_wallet-snapshot-service` share one
database but have separate migration histories.

If the `py_wallet` schema changes, update `app/models/external.py`. Snapshot-service
migrations should stay limited to snapshot-owned tables.

## Metrics

Prometheus metrics include:

- `snapshot_service_build_info`
- `snapshot_worker_jobs_total`
- `snapshot_worker_job_duration_seconds`
- `snapshot_worker_chain_requests_total`
- `snapshot_worker_chain_duration_seconds`
- `snapshot_worker_rpc_latency_seconds`
- `snapshot_worker_rpc_attempts_total`
- `snapshot_worker_rpc_failovers_total`
- `snapshot_worker_rpc_circuit_open_total`
- `snapshot_worker_pending_jobs`
- `snapshot_worker_running_jobs`
- `snapshot_worker_oldest_pending_job_age_seconds`
- `snapshot_worker_heartbeat_timestamp_seconds`
- `snapshot_scheduler_heartbeat_timestamp_seconds`
- `snapshot_background_tick_errors_total`
- `snapshot_database_errors_total`
- `snapshot_worker_last_success_timestamp`
- `snapshot_worker_last_job_completion_timestamp_seconds`
- `snapshot_worker_last_job_success_timestamp_seconds`
- `snapshot_worker_chain_last_success_timestamp_seconds`
- `snapshot_worker_wallets_processed_total`
- `snapshot_worker_balance_snapshots_written_total`
- `snapshot_scheduler_jobs_created_total`
- `snapshot_jobs_enqueued_total`
- `snapshot_jobs_skipped_total`

All metric labels are deliberately low-cardinality. Wallet addresses, user IDs,
wallet IDs, job IDs, RPC URLs, and error messages must not be used as labels.

## Tests And Quality

Run tests:

```bash
.venv/bin/python -m pytest
```

Run linting:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The test suite uses SQLite fixtures and covers health/API behavior, job creation,
worker claiming, scheduler job creation, manual wallet handling, and partial success
processing.

## Current Limits

- Exchange wallets are not implemented yet.
- User-defined chains and token contracts are not implemented yet.
- Web, worker, and scheduler are not split into separate runtime processes yet.
- Kubernetes manifests and dashboards are expected to live in infrastructure code.
