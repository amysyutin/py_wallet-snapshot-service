from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.enums import JobStatus, ScopeType, TriggerType
from app.metrics import (
    background_tick_errors_total,
    database_errors_total,
    oldest_pending_job_age_seconds,
    pending_jobs,
    running_jobs,
    worker_heartbeat_timestamp_seconds,
)
from app.models.snapshots import SnapshotRun
from app.worker.loop import WorkerLoop


@pytest.mark.asyncio
async def test_worker_continues_after_tick_error(caplog):
    loop = WorkerLoop()
    errors_before = background_tick_errors_total.labels("worker")._value.get()
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    calls = 0

    def refresh(_db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database error")
        loop.stop()

    with (
        patch("app.worker.loop.SessionLocal", return_value=session_context),
        patch.object(loop, "_refresh_job_gauges", side_effect=refresh),
        patch("app.worker.loop.claim_next_pending_job", return_value=None),
        patch("app.worker.loop.asyncio.sleep", new_callable=AsyncMock),
    ):
        await loop.run()

    assert calls == 2
    assert "snapshot_worker_tick_failed" in caplog.text
    assert background_tick_errors_total.labels("worker")._value.get() == errors_before + 1
    assert worker_heartbeat_timestamp_seconds._value.get() > 0


def test_worker_refreshes_queue_depth_and_oldest_pending_age(db_session):
    created_at = datetime.now(UTC) - timedelta(seconds=90)
    db_session.add_all(
        [
            SnapshotRun(
                user_id=1,
                trigger_type=TriggerType.MANUAL.value,
                scope_type=ScopeType.ALL.value,
                status=JobStatus.PENDING.value,
                created_at=created_at,
            ),
            SnapshotRun(
                user_id=2,
                trigger_type=TriggerType.MANUAL.value,
                scope_type=ScopeType.ALL.value,
                status=JobStatus.RUNNING.value,
                created_at=created_at,
            ),
        ]
    )
    db_session.commit()

    WorkerLoop._refresh_job_gauges(db_session)

    assert pending_jobs._value.get() == 1
    assert running_jobs._value.get() == 1
    assert oldest_pending_job_age_seconds._value.get() >= 89


@pytest.mark.asyncio
async def test_worker_counts_database_tick_errors():
    loop = WorkerLoop()
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    errors_before = database_errors_total.labels("worker")._value.get()
    calls = 0

    def refresh(_db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SQLAlchemyError("temporary database error")
        loop.stop()

    with (
        patch("app.worker.loop.SessionLocal", return_value=session_context),
        patch.object(loop, "_refresh_job_gauges", side_effect=refresh),
        patch("app.worker.loop.claim_next_pending_job", return_value=None),
        patch("app.worker.loop.asyncio.sleep", new_callable=AsyncMock),
    ):
        await loop.run()

    assert database_errors_total.labels("worker")._value.get() == errors_before + 1


@pytest.mark.asyncio
async def test_worker_reuses_one_evm_collector_across_jobs():
    collector = MagicMock()
    loop = WorkerLoop(evm_collector=collector)
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    jobs = [MagicMock(id=1), MagicMock(id=2)]

    def claim_job(_db):
        if jobs:
            return jobs.pop(0)
        loop.stop()
        return None

    with (
        patch("app.worker.loop.SessionLocal", return_value=session_context),
        patch.object(loop, "_refresh_job_gauges"),
        patch("app.worker.loop.claim_next_pending_job", side_effect=claim_job),
        patch("app.worker.loop.asyncio.sleep", new_callable=AsyncMock),
        patch("app.worker.loop.SnapshotProcessor") as processor,
    ):
        await loop.run()

    assert processor.call_count == 2
    assert all(call.kwargs["evm_collector"] is collector for call in processor.call_args_list)
    collector.close.assert_called_once_with()
