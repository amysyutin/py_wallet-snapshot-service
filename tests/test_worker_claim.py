from datetime import UTC, datetime

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import SnapshotRun
from app.worker.claim import claim_next_pending_job


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

    job = claim_next_pending_job(db_session)

    assert job is not None
    assert job.status == JobStatus.RUNNING.value
    assert job.started_at is not None


def test_no_pending_job_returns_none(db_session):
    assert claim_next_pending_job(db_session) is None


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

    first = claim_next_pending_job(db_session)
    second = claim_next_pending_job(db_session)

    assert first is not None
    assert second is None

