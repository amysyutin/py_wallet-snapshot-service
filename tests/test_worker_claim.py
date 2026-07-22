from datetime import UTC, datetime, timedelta

import pytest

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import SnapshotRun
from app.worker.claim import (
    JobLeaseLostError,
    claim_next_pending_job,
    recover_stale_running_jobs,
    renew_job_lease,
)

WORKER_ID = "worker-test-1"
LEASE_SECONDS = 1800


def test_pending_job_can_be_claimed(db_session):
    db_session.add(
        SnapshotRun(
            user_id=1,
            trigger_type=TriggerType.MANUAL.value,
            scope_type=ScopeType.ALL.value,
            status=JobStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    job = claim_next_pending_job(
        db_session,
        worker_id=WORKER_ID,
        lease_seconds=LEASE_SECONDS,
    )

    assert job is not None
    assert job.status == JobStatus.RUNNING.value
    assert job.started_at is not None
    assert job.worker_id == WORKER_ID
    assert job.lease_expires_at is not None


def test_no_pending_job_returns_none(db_session):
    assert (
        claim_next_pending_job(
            db_session,
            worker_id=WORKER_ID,
            lease_seconds=LEASE_SECONDS,
        )
        is None
    )


def test_double_claim_does_not_claim_same_job_twice(db_session):
    db_session.add(
        SnapshotRun(
            user_id=1,
            trigger_type=TriggerType.MANUAL.value,
            scope_type=ScopeType.ALL.value,
            status=JobStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    first = claim_next_pending_job(
        db_session,
        worker_id=WORKER_ID,
        lease_seconds=LEASE_SECONDS,
    )
    second = claim_next_pending_job(
        db_session,
        worker_id="worker-test-2",
        lease_seconds=LEASE_SECONDS,
    )

    assert first is not None
    assert second is None


def test_expired_running_job_is_failed_and_unblocks_queue(db_session):
    now = datetime.now(UTC)
    stale = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.SCHEDULED.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1),
        worker_id="dead-worker",
        lease_expires_at=now - timedelta(seconds=1),
    )
    db_session.add(stale)
    db_session.commit()

    recovered = recover_stale_running_jobs(
        db_session,
        lease_seconds=LEASE_SECONDS,
        now=now,
    )
    db_session.commit()
    db_session.refresh(stale)

    assert recovered == 1
    assert stale.status == JobStatus.FAILED.value
    assert stale.finished_at.replace(tzinfo=UTC) == now
    assert stale.worker_id is None
    assert stale.lease_expires_at is None
    assert stale.error_message == "worker lease expired before job completion"


def test_legacy_running_job_without_lease_is_recovered(db_session):
    now = datetime.now(UTC)
    stale = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.SCHEDULED.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1),
    )
    db_session.add(stale)
    db_session.commit()

    recovered = recover_stale_running_jobs(
        db_session,
        lease_seconds=LEASE_SECONDS,
        now=now,
    )

    assert recovered == 1
    assert stale.status == JobStatus.FAILED.value


def test_active_lease_is_not_recovered(db_session):
    now = datetime.now(UTC)
    active = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.SCHEDULED.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=now,
        started_at=now,
        worker_id=WORKER_ID,
        lease_expires_at=now + timedelta(minutes=10),
    )
    db_session.add(active)
    db_session.commit()

    recovered = recover_stale_running_jobs(
        db_session,
        lease_seconds=LEASE_SECONDS,
        now=now,
    )

    assert recovered == 0
    assert active.status == JobStatus.RUNNING.value


def test_lease_can_only_be_renewed_by_owning_worker(db_session):
    now = datetime.now(UTC)
    job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.MANUAL.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=now,
        started_at=now,
        worker_id=WORKER_ID,
        lease_expires_at=now + timedelta(minutes=5),
    )
    db_session.add(job)
    db_session.commit()

    renewed_until = renew_job_lease(
        db_session,
        job_id=job.id,
        worker_id=WORKER_ID,
        lease_seconds=LEASE_SECONDS,
        now=now,
    )
    assert renewed_until == now + timedelta(seconds=LEASE_SECONDS)

    with pytest.raises(JobLeaseLostError):
        renew_job_lease(
            db_session,
            job_id=job.id,
            worker_id="other-worker",
            lease_seconds=LEASE_SECONDS,
            now=now,
        )
