import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import SessionLocal
from app.enums import JobStatus
from app.metrics import (
    background_tick_errors_total,
    database_errors_total,
    oldest_pending_job_age_seconds,
    pending_jobs,
    running_jobs,
    worker_heartbeat_timestamp_seconds,
)
from app.models.snapshots import SnapshotRun
from app.services.snapshot_processor import SnapshotProcessor
from app.worker.claim import claim_next_pending_job

logger = logging.getLogger(__name__)


class WorkerLoop:
    def __init__(self):
        self._stop = asyncio.Event()

    async def run(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            worker_heartbeat_timestamp_seconds.set(datetime.now(UTC).timestamp())
            try:
                with SessionLocal() as db:
                    self._refresh_job_gauges(db)
                    job = claim_next_pending_job(db)
                    if job is None:
                        await asyncio.sleep(settings.snapshot_worker_poll_seconds)
                        continue
                    try:
                        SnapshotProcessor(db).process(job)
                    except Exception as exc:
                        logger.exception(
                            "snapshot_job_failed",
                            extra={"job_id": job.id, "error_type": "unknown"},
                        )
                        job.status = JobStatus.FAILED.value
                        job.error_message = str(exc)[:500]
                        db.commit()
            except SQLAlchemyError:
                database_errors_total.labels("worker").inc()
                background_tick_errors_total.labels("worker").inc()
                logger.exception("snapshot_worker_database_tick_failed")
                await asyncio.sleep(settings.snapshot_worker_poll_seconds)
            except Exception:
                background_tick_errors_total.labels("worker").inc()
                logger.exception("snapshot_worker_tick_failed")
                await asyncio.sleep(settings.snapshot_worker_poll_seconds)

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _refresh_job_gauges(db) -> None:
        rows = dict(
            db.execute(
                select(SnapshotRun.status, func.count(SnapshotRun.id)).group_by(SnapshotRun.status)
            ).all()
        )
        pending_jobs.set(rows.get(JobStatus.PENDING.value, 0))
        running_jobs.set(rows.get(JobStatus.RUNNING.value, 0))
        oldest_pending_created_at = db.scalar(
            select(func.min(SnapshotRun.created_at)).where(
                SnapshotRun.status == JobStatus.PENDING.value
            )
        )
        if oldest_pending_created_at is None:
            oldest_pending_job_age_seconds.set(0)
            return
        if oldest_pending_created_at.tzinfo is None:
            oldest_pending_created_at = oldest_pending_created_at.replace(tzinfo=UTC)
        age_seconds = (datetime.now(UTC) - oldest_pending_created_at).total_seconds()
        oldest_pending_job_age_seconds.set(max(age_seconds, 0))


async def run_worker_forever() -> None:
    loop = WorkerLoop()
    with contextlib.suppress(asyncio.CancelledError):
        await loop.run()
