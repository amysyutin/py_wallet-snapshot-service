from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import SnapshotRun
from app.scheduler.loop import create_scheduled_jobs
from tests.conftest import seed_user_wallet


def test_scheduler_creates_scheduled_job(db_session):
    seed_user_wallet(db_session)

    created = create_scheduled_jobs(db_session)

    assert created == 1
    assert db_session.query(SnapshotRun).one().trigger_type == TriggerType.SCHEDULED.value


def test_scheduler_does_not_create_duplicate_pending_job(db_session):
    seed_user_wallet(db_session)
    db_session.add(
        SnapshotRun(
            user_id=1,
            trigger_type=TriggerType.SCHEDULED.value,
            scope_type=ScopeType.ALL.value,
            status=JobStatus.PENDING.value,
        )
    )
    db_session.commit()

    created = create_scheduled_jobs(db_session)

    assert created == 0
    assert db_session.query(SnapshotRun).count() == 1

