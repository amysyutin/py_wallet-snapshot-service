import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy import exists, select

from app.config import get_settings
from app.db import SessionLocal
from app.enums import JobStatus, ScopeType, TriggerType
from app.metrics import scheduler_jobs_created_total
from app.models.external import User, Wallet
from app.models.snapshots import SnapshotRun

logger = logging.getLogger(__name__)


class SchedulerLoop:
    def __init__(self):
        self._stop = asyncio.Event()

    async def run(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            with SessionLocal() as db:
                create_scheduled_jobs(db)
            await asyncio.sleep(settings.snapshot_interval_seconds)

    def stop(self) -> None:
        self._stop.set()


def create_scheduled_jobs(db) -> int:
    active_users = db.scalars(
        select(User)
        .where(User.is_active.is_(True))
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
    return created


async def run_scheduler_forever() -> None:
    loop = SchedulerLoop()
    with contextlib.suppress(asyncio.CancelledError):
        await loop.run()
