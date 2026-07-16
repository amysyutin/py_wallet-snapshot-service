from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()

build_info = Gauge(
    "snapshot_service_build_info",
    "Build identity for the running snapshot service.",
    ["service", "version", "build_sha", "environment"],
    registry=registry,
)

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
rpc_attempts_total = Counter(
    "snapshot_worker_rpc_attempts_total",
    "RPC endpoint attempts.",
    ["chain", "provider", "outcome", "error_type"],
    registry=registry,
)
rpc_failovers_total = Counter(
    "snapshot_worker_rpc_failovers_total",
    "RPC failovers to another configured endpoint.",
    ["chain"],
    registry=registry,
)
rpc_circuit_open_total = Counter(
    "snapshot_worker_rpc_circuit_open_total",
    "RPC endpoints temporarily removed from rotation.",
    ["chain", "provider"],
    registry=registry,
)
pending_jobs = Gauge("snapshot_worker_pending_jobs", "Pending snapshot jobs.", registry=registry)
running_jobs = Gauge("snapshot_worker_running_jobs", "Running snapshot jobs.", registry=registry)
oldest_pending_job_age_seconds = Gauge(
    "snapshot_worker_oldest_pending_job_age_seconds",
    "Age in seconds of the oldest pending snapshot job, or zero when the queue is empty.",
    registry=registry,
)
worker_heartbeat_timestamp_seconds = Gauge(
    "snapshot_worker_heartbeat_timestamp_seconds",
    "Unix timestamp of the most recent worker loop heartbeat.",
    registry=registry,
)
scheduler_heartbeat_timestamp_seconds = Gauge(
    "snapshot_scheduler_heartbeat_timestamp_seconds",
    "Unix timestamp of the most recent scheduler loop heartbeat.",
    registry=registry,
)
background_tick_errors_total = Counter(
    "snapshot_background_tick_errors_total",
    "Errors raised by a background loop tick.",
    ["component"],
    registry=registry,
)
database_errors_total = Counter(
    "snapshot_database_errors_total",
    "Database errors encountered by a service component.",
    ["component"],
    registry=registry,
)
last_success_timestamp = Gauge(
    "snapshot_worker_last_success_timestamp",
    "Unix timestamp of the last successful snapshot job.",
    registry=registry,
)
last_job_completion_timestamp_seconds = Gauge(
    "snapshot_worker_last_job_completion_timestamp_seconds",
    "Unix timestamp of the most recent completed job by status and trigger type.",
    ["status", "trigger_type"],
    registry=registry,
)
last_job_success_timestamp_seconds = Gauge(
    "snapshot_worker_last_job_success_timestamp_seconds",
    "Unix timestamp of the most recent successful job by trigger and scope type.",
    ["trigger_type", "scope_type"],
    registry=registry,
)
chain_last_success_timestamp_seconds = Gauge(
    "snapshot_worker_chain_last_success_timestamp_seconds",
    "Unix timestamp of the most recent successful collection by chain.",
    ["chain"],
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
jobs_enqueued_total = Counter(
    "snapshot_jobs_enqueued_total",
    "Snapshot jobs added to the queue.",
    ["source", "trigger_type", "scope_type"],
    registry=registry,
)
jobs_skipped_total = Counter(
    "snapshot_jobs_skipped_total",
    "Snapshot jobs not added to the queue.",
    ["source", "reason"],
    registry=registry,
)


def configure_build_info(*, service: str, version: str, build_sha: str, environment: str) -> None:
    """Expose exactly one identity series for the current process."""
    build_info.clear()
    build_info.labels(service, version, build_sha, environment).set(1)
