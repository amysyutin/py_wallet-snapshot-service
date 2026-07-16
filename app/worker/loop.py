import asyncio
import contextlib
import logging

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.enums import JobStatus
from app.metrics import pending_jobs, running_jobs
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
            except Exception:
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


async def run_worker_forever() -> None:
    loop = WorkerLoop()
    with contextlib.suppress(asyncio.CancelledError):
        await loop.run()
