from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.enums import JobStatus
from app.metrics import stale_jobs_recovered_total
from app.models.snapshots import SnapshotRun


class JobLeaseLostError(RuntimeError):
    pass


def recover_stale_running_jobs(
    db: Session,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    legacy_cutoff = now - timedelta(seconds=lease_seconds)
    stmt = select(SnapshotRun).where(
        SnapshotRun.status == JobStatus.RUNNING.value,
        or_(
            SnapshotRun.lease_expires_at <= now,
            and_(
                SnapshotRun.lease_expires_at.is_(None),
                or_(
                    SnapshotRun.started_at <= legacy_cutoff,
                    and_(
                        SnapshotRun.started_at.is_(None),
                        SnapshotRun.created_at <= legacy_cutoff,
                    ),
                ),
            ),
        ),
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    stale_jobs = list(db.scalars(stmt))
    for job in stale_jobs:
        lease_state = "expired_lease" if job.lease_expires_at is not None else "legacy_no_lease"
        job.status = JobStatus.FAILED.value
        job.finished_at = now
        job.error_message = "worker lease expired before job completion"
        job.worker_id = None
        job.lease_expires_at = None
        stale_jobs_recovered_total.labels(lease_state).inc()
    return len(stale_jobs)


def renew_job_lease(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    result = db.execute(
        update(SnapshotRun)
        .where(
            SnapshotRun.id == job_id,
            SnapshotRun.status == JobStatus.RUNNING.value,
            SnapshotRun.worker_id == worker_id,
        )
        .values(lease_expires_at=lease_expires_at)
    )
    if result.rowcount != 1:
        db.rollback()
        raise JobLeaseLostError(f"snapshot job {job_id} lease is no longer owned by this worker")
    db.commit()
    return lease_expires_at


def claim_next_pending_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int,
) -> SnapshotRun | None:
    now = datetime.now(UTC)
    recover_stale_running_jobs(db, lease_seconds=lease_seconds, now=now)
    stmt = (
        select(SnapshotRun)
        .where(SnapshotRun.status == JobStatus.PENDING.value)
        .order_by(SnapshotRun.created_at, SnapshotRun.id)
        .limit(1)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = db.scalar(stmt)
    if job is None:
        db.commit()
        return None

    job.status = JobStatus.RUNNING.value
    job.started_at = now
    job.worker_id = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(job)
    return job
