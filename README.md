# py_wallet-snapshot-service

MVP-friendly snapshot microservice for `py_wallet`. It creates snapshot jobs, loads active wallets from the shared PostgreSQL database, collects EVM native balances through RPC, includes manual balances, writes portfolio snapshot rows back to PostgreSQL, and exposes operational metrics for Prometheus.

Prometheus is used only for operational telemetry. Portfolio balances are stored in PostgreSQL and should be read by `py_wallet-api`.

```text
Snapshot Service -> EVM RPC / price providers -> PostgreSQL
py_wallet-api    -> PostgreSQL -> Frontend
Prometheus       -> /metrics from services -> Grafana/alerts
```

## What It Does

- Exposes FastAPI endpoints for health, metrics, debug jobs, and internal job creation.
- Creates scheduled/manual/retry snapshot jobs.
- Runs local background scheduler and worker loops in one process.
- Claims jobs with PostgreSQL row-level locking using `FOR UPDATE SKIP LOCKED`.
- Reads API-owned tables: `users`, `wallet_groups`, `wallets`, `manual_balances`, `assets`.
- Owns snapshot tables: `snapshot_runs`, `wallet_snapshots`, `chain_snapshots`, `snapshot_balance_snapshots`.
- Collects EVM native balances with JSON-RPC `eth_getBalance`.
- Processes manual wallets without RPC.
- Uses CoinGecko with static local fallback prices for common symbols.
- Represents partial success at wallet and job level.

## What It Does Not Do Yet

No Redis, Celery, RabbitMQ, Kafka, Docker, Kubernetes, private keys, signing, transactions, exchange integrations, Binance, custom user networks, or custom token contracts in this first version.

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `DATABASE_URL` in `.env`, then run snapshot-owned migrations:

```bash
alembic upgrade head
```

Start the local service:

```bash
uvicorn app.main:app --reload --port 8001
```

For local API-only testing, you can set:

```env
SNAPSHOT_WORKER_ENABLED=false
SNAPSHOT_SCHEDULER_ENABLED=false
```

## Environment

Important variables:

- `DATABASE_URL`
- `INTERNAL_API_TOKEN`
- `SNAPSHOT_WORKER_ENABLED`
- `SNAPSHOT_SCHEDULER_ENABLED`
- `SNAPSHOT_INTERVAL_SECONDS`
- `SNAPSHOT_WORKER_POLL_SECONDS`
- `DEBUG_ENDPOINTS_ENABLED`
- `ETHEREUM_RPC_URL`
- `BASE_RPC_URL`
- `ARBITRUM_RPC_URL`
- `BNB_RPC_URL`
- `LINEA_RPC_URL`
- `COINGECKO_BASE_URL`

See `.env.example` for the full list.

## API Examples

Health:

```bash
curl http://localhost:8001/health
```

Metrics:

```bash
curl http://localhost:8001/metrics
```

Debug jobs:

```bash
curl http://localhost:8001/debug/jobs
```

Create a manual snapshot job:

```bash
curl -X POST http://localhost:8001/internal/snapshot-jobs \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: change-me' \
  -d '{"user_id":1,"trigger_type":"manual","scope_type":"all"}'
```

Retry failed chains from a parent job:

```bash
curl -X POST http://localhost:8001/internal/snapshot-jobs/123/retry-failed \
  -H 'X-Internal-Token: change-me'
```

Retry jobs currently store `parent_run_id` and reprocess the parent scope. Exact failed-chain-only collection is intentionally left for a later iteration.

## Worker And Scheduler

The scheduler only creates `scheduled/all/pending` jobs for active users who have active wallets. It does not call RPC.

The worker loop:

1. claims the oldest pending job;
2. marks it `running`;
3. processes wallets outside the claim transaction;
4. writes wallet, chain, and balance snapshots;
5. marks the job `success`, `partial_success`, or `failed`.

Missing RPC URLs are recorded as failed chain snapshots with `error_type=missing_rpc_url`; other chains continue.

## Metrics

Exposed Prometheus metrics include:

- `snapshot_worker_jobs_total`
- `snapshot_worker_job_duration_seconds`
- `snapshot_worker_chain_requests_total`
- `snapshot_worker_chain_duration_seconds`
- `snapshot_worker_rpc_latency_seconds`
- `snapshot_worker_pending_jobs`
- `snapshot_worker_running_jobs`
- `snapshot_worker_last_success_timestamp`
- `snapshot_worker_wallets_processed_total`
- `snapshot_worker_balance_snapshots_written_total`
- `snapshot_scheduler_jobs_created_total`

## Tests

```bash
pytest
```

The tests use SQLite fixtures for API, scheduler, worker claim, manual wallet processing, and partial success behavior.

## Schema Assumptions

`py_wallet-api` owns these tables and columns:

- `users(id, email, is_active)`
- `wallet_groups(id, user_id, name)`
- `wallets(id, user_id, group_id, label, address, chain_type, wallet_type, is_active)`
- `assets(id, symbol, name, coingecko_id)`
- `manual_balances(wallet_id, asset_id, amount, price_usd)` with symbols read from `assets`

If the real `py_wallet-api` schema differs, update `app/models/external.py`. Alembic migrations in this repo are intentionally limited to snapshot-owned tables.

## Roadmap

- ERC-20 token collection.
- Exact failed-chain retry processing.
- Separate web/worker/scheduler runtime modes.
- Docker and compose in infra repo.
- Binance/exchange wallet support.
- User-defined chains and token contracts.
- Grafana dashboards and alerting rules.
