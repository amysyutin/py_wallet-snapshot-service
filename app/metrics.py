from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()

jobs_total = Counter(
    "snapshot_worker_jobs_total",
    "Snapshot worker jobs processed.",
    ["status", "trigger_type", "scope_type"],
    registry=registry,
)
job_duration_seconds = Histogram(
    "snapshot_worker_job_duration_seconds",
    "Snapshot job processing duration.",
    ["status", "trigger_type", "scope_type"],
    registry=registry,
)
chain_requests_total = Counter(
    "snapshot_worker_chain_requests_total",
    "Chain collection requests.",
    ["chain", "status", "error_type"],
    registry=registry,
)
chain_duration_seconds = Histogram(
    "snapshot_worker_chain_duration_seconds",
    "Chain collection duration.",
    ["chain", "status"],
    registry=registry,
)
rpc_latency_seconds = Histogram(
    "snapshot_worker_rpc_latency_seconds",
    "RPC latency by chain.",
    ["chain"],
    registry=registry,
)
pending_jobs = Gauge("snapshot_worker_pending_jobs", "Pending snapshot jobs.", registry=registry)
running_jobs = Gauge("snapshot_worker_running_jobs", "Running snapshot jobs.", registry=registry)
last_success_timestamp = Gauge(
    "snapshot_worker_last_success_timestamp",
    "Unix timestamp of the last successful snapshot job.",
    registry=registry,
)
wallets_processed_total = Counter(
    "snapshot_worker_wallets_processed_total",
    "Wallet snapshots processed.",
    ["status"],
    registry=registry,
)
balance_snapshots_written_total = Counter(
    "snapshot_worker_balance_snapshots_written_total",
    "Balance snapshots written.",
    registry=registry,
)
scheduler_jobs_created_total = Counter(
    "snapshot_scheduler_jobs_created_total",
    "Scheduler job creation attempts.",
    ["result"],
    registry=registry,
)
