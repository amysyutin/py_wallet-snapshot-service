from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import JobStatus
from app.models.snapshots import SnapshotRun


def claim_next_pending_job(db: Session) -> SnapshotRun | None:
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
    job.started_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job
