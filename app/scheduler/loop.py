import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import SessionLocal
from app.enums import JobStatus, ScopeType, TriggerType
from app.metrics import (
    background_tick_errors_total,
    database_errors_total,
    jobs_enqueued_total,
    jobs_skipped_total,
    scheduler_heartbeat_timestamp_seconds,
    scheduler_jobs_created_total,
)
from app.models.external import User, Wallet
from app.models.snapshots import SnapshotRun

logger = logging.getLogger(__name__)


class SchedulerLoop:
    def __init__(self):
        self._stop = asyncio.Event()

    async def run(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            scheduler_heartbeat_timestamp_seconds.set(datetime.now(UTC).timestamp())
            try:
                with SessionLocal() as db:
                    create_scheduled_jobs(db)
            except SQLAlchemyError:
                database_errors_total.labels("scheduler").inc()
                background_tick_errors_total.labels("scheduler").inc()
                logger.exception("scheduled_snapshot_database_tick_failed")
            except Exception:
                background_tick_errors_total.labels("scheduler").inc()
                logger.exception("scheduled_snapshot_tick_failed")
            await asyncio.sleep(settings.snapshot_interval_seconds)

    def stop(self) -> None:
        self._stop.set()


def create_scheduled_jobs(db) -> int:
    active_users = db.scalars(
        select(User)
        .where(exists().where(Wallet.user_id == User.id, Wallet.is_active.is_(True)))
        .order_by(User.id)
    ).all()
    created = 0
    for user in active_users:
        existing = db.scalar(
            select(SnapshotRun.id)
            .where(
                SnapshotRun.user_id == user.id,
                SnapshotRun.trigger_type == TriggerType.SCHEDULED.value,
                SnapshotRun.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
            )
            .limit(1)
        )
        if existing:
            scheduler_jobs_created_total.labels("skipped_existing_pending").inc()
            jobs_skipped_total.labels("scheduler", "existing_pending").inc()
            logger.info(
                "scheduled_snapshot_job_skipped_existing_pending", extra={"user_id": user.id}
            )
            continue
        db.add(
            SnapshotRun(
                user_id=user.id,
                trigger_type=TriggerType.SCHEDULED.value,
                scope_type=ScopeType.ALL.value,
                status=JobStatus.PENDING.value,
                created_at=datetime.now(UTC),
            )
        )
        created += 1
        scheduler_jobs_created_total.labels("created").inc()
        logger.info("scheduled_snapshot_job_created", extra={"user_id": user.id})
    db.commit()
    if created:
        jobs_enqueued_total.labels(
            "scheduler", TriggerType.SCHEDULED.value, ScopeType.ALL.value
        ).inc(created)
    return created


async def run_scheduler_forever() -> None:
    loop = SchedulerLoop()
    with contextlib.suppress(asyncio.CancelledError):
        await loop.run()
