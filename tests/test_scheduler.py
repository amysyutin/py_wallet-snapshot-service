from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import SnapshotRun
from app.scheduler.loop import SchedulerLoop, create_scheduled_jobs
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


@pytest.mark.asyncio
async def test_scheduler_continues_after_tick_error(caplog):
    loop = SchedulerLoop()
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    calls = 0

    def tick(_db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database error")
        loop.stop()

    with (
        patch("app.scheduler.loop.SessionLocal", return_value=session_context),
        patch("app.scheduler.loop.create_scheduled_jobs", side_effect=tick),
        patch("app.scheduler.loop.asyncio.sleep", new_callable=AsyncMock),
    ):
        await loop.run()

    assert calls == 2
    assert "scheduled_snapshot_tick_failed" in caplog.text
