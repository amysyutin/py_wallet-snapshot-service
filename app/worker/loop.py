import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from uuid import uuid4

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
from app.services.chain_config import get_chain_configs
from app.services.evm_collector import EvmCollector
from app.services.price_service import PriceService
from app.services.snapshot_processor import SnapshotProcessor
from app.worker.claim import JobLeaseLostError, claim_next_pending_job

logger = logging.getLogger(__name__)


class WorkerLoop:
    def __init__(self, evm_collector: EvmCollector | None = None):
        self._stop = asyncio.Event()
        self.worker_id = str(uuid4())
        settings = get_settings()
        self.evm_collector = evm_collector or EvmCollector(
            get_chain_configs(settings),
            PriceService(settings),
            cooldown_seconds=settings.rpc_cooldown_seconds,
        )

    async def run(self) -> None:
        settings = get_settings()
        try:
            while not self._stop.is_set():
                worker_heartbeat_timestamp_seconds.set(datetime.now(UTC).timestamp())
                try:
                    with SessionLocal() as db:
                        self._refresh_job_gauges(db)
                        job = claim_next_pending_job(
                            db,
                            worker_id=self.worker_id,
                            lease_seconds=settings.snapshot_job_lease_seconds,
                        )
                        if job is None:
                            await asyncio.sleep(settings.snapshot_worker_poll_seconds)
                            continue
                        try:
                            SnapshotProcessor(
                                db,
                                evm_collector=self.evm_collector,
                                worker_id=self.worker_id,
                                lease_seconds=settings.snapshot_job_lease_seconds,
                            ).process(job)
                        except JobLeaseLostError:
                            logger.warning(
                                "snapshot_job_lease_lost",
                                extra={"job_id": job.id, "worker_id": self.worker_id},
                            )
                        except Exception as exc:
                            logger.exception(
                                "snapshot_job_failed",
                                extra={"job_id": job.id, "error_type": "unknown"},
                            )
                            job.status = JobStatus.FAILED.value
                            job.finished_at = datetime.now(UTC)
                            job.error_message = str(exc)[:500]
                            job.worker_id = None
                            job.lease_expires_at = None
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
        finally:
            self.evm_collector.close()

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
