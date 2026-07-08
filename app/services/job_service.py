from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import ChainSnapshot, SnapshotRun
from app.schemas.jobs import SnapshotJobCreate


class JobService:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, payload: SnapshotJobCreate) -> SnapshotRun:
        job = SnapshotRun(
            user_id=payload.user_id,
            trigger_type=payload.trigger_type.value,
            scope_type=payload.scope_type.value,
            group_id=payload.group_id,
            wallet_id=payload.wallet_id,
            parent_run_id=None,
            status=JobStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: int) -> SnapshotRun:
        job = self.db.get(SnapshotRun, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    def create_retry_failed_job(self, parent_job_id: int) -> SnapshotRun:
        parent = self.db.get(SnapshotRun, parent_job_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent job not found")

        failed_chain_exists = self.db.scalar(
            select(ChainSnapshot.id)
            .join(ChainSnapshot.wallet_snapshot)
            .where(ChainSnapshot.status == "failed", ChainSnapshot.wallet_snapshot.has(snapshot_run_id=parent.id))
            .limit(1)
        )
        if failed_chain_exists is None:
            raise HTTPException(status_code=400, detail="parent job has no failed chains")

        job = SnapshotRun(
            user_id=parent.user_id,
            trigger_type=TriggerType.RETRY.value,
            scope_type=ScopeType.FAILED_CHAINS.value,
            group_id=parent.group_id,
            wallet_id=parent.wallet_id,
            parent_run_id=parent.id,
            status=JobStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job
