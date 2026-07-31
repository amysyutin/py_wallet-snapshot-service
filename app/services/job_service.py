from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import blake2b
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.enums import JobStatus, ScopeType, TriggerType
from app.metrics import jobs_enqueued_total
from app.models.snapshots import ChainSnapshot, SnapshotRun
from app.schemas.jobs import SnapshotJobCreate


@dataclass(frozen=True)
class JobCreationResult:
    job: SnapshotRun
    reused: bool


class JobService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _active_scope_lock_key(payload: SnapshotJobCreate) -> int:
        scope = (
            f"{payload.user_id}:{payload.scope_type.value}:"
            f"{payload.group_id or 0}:{payload.wallet_id or 0}"
        )
        return int.from_bytes(
            blake2b(scope.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )

    def _lock_active_scope(self, payload: SnapshotJobCreate) -> None:
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": self._active_scope_lock_key(payload)},
        )

    def _get_active_scope_job(self, payload: SnapshotJobCreate) -> SnapshotRun | None:
        query = select(SnapshotRun).where(
            SnapshotRun.user_id == payload.user_id,
            SnapshotRun.scope_type == payload.scope_type.value,
            SnapshotRun.status.in_((JobStatus.PENDING.value, JobStatus.RUNNING.value)),
        )
        if payload.group_id is None:
            query = query.where(SnapshotRun.group_id.is_(None))
        else:
            query = query.where(SnapshotRun.group_id == payload.group_id)
        if payload.wallet_id is None:
            query = query.where(SnapshotRun.wallet_id.is_(None))
        else:
            query = query.where(SnapshotRun.wallet_id == payload.wallet_id)
        return self.db.scalar(query.order_by(SnapshotRun.id.desc()).limit(1))

    def create_job(
        self,
        payload: SnapshotJobCreate,
        *,
        source: Literal["api", "scheduler"] = "api",
    ) -> JobCreationResult:
        self._lock_active_scope(payload)
        active_job = self._get_active_scope_job(payload)
        if active_job is not None:
            self.db.commit()
            return JobCreationResult(job=active_job, reused=True)

        job = SnapshotRun(
            user_id=payload.user_id,
            trigger_type=payload.trigger_type.value,
            scope_type=payload.scope_type.value,
            group_id=payload.group_id,
            wallet_id=payload.wallet_id,
            parent_run_id=None,
            activation_channel=payload.activation_channel,
            status=JobStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        jobs_enqueued_total.labels(source, job.trigger_type, job.scope_type).inc()
        return JobCreationResult(job=job, reused=False)

    def get_job(self, job_id: int) -> SnapshotRun:
        job = self.db.get(SnapshotRun, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @staticmethod
    def _retry_lock_key(parent_job_id: int) -> int:
        scope = f"retry:{parent_job_id}"
        return int.from_bytes(
            blake2b(scope.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )

    def _lock_retry_parent(self, parent_job_id: int) -> None:
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": self._retry_lock_key(parent_job_id)},
        )

    def create_retry_failed_job(self, parent_job_id: int) -> JobCreationResult:
        self._lock_retry_parent(parent_job_id)
        parent = self.db.get(SnapshotRun, parent_job_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent job not found")
        if parent.status not in (
            JobStatus.PARTIAL_SUCCESS.value,
            JobStatus.FAILED.value,
        ):
            raise HTTPException(
                status_code=409,
                detail="parent job is not ready for failed-chain retry",
            )

        failed_chain_exists = self.db.scalar(
            select(ChainSnapshot.id)
            .join(ChainSnapshot.wallet_snapshot)
            .where(
                ChainSnapshot.status == "failed",
                ChainSnapshot.wallet_snapshot.has(snapshot_run_id=parent.id),
            )
            .limit(1)
        )
        if failed_chain_exists is None:
            raise HTTPException(status_code=400, detail="parent job has no failed chains")

        active_retry = self.db.scalar(
            select(SnapshotRun)
            .where(
                SnapshotRun.parent_run_id == parent.id,
                SnapshotRun.trigger_type == TriggerType.RETRY.value,
                SnapshotRun.scope_type == ScopeType.FAILED_CHAINS.value,
                SnapshotRun.status.in_((JobStatus.PENDING.value, JobStatus.RUNNING.value)),
            )
            .order_by(SnapshotRun.id.desc())
            .limit(1)
        )
        if active_retry is not None:
            self.db.commit()
            return JobCreationResult(job=active_retry, reused=True)

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
        jobs_enqueued_total.labels("api", job.trigger_type, job.scope_type).inc()
        return JobCreationResult(job=job, reused=False)
