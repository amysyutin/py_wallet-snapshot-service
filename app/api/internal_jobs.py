from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import require_internal_token
from app.db import get_db
from app.schemas.jobs import SnapshotJobCreate, SnapshotJobCreateResponse, SnapshotJobStatusResponse
from app.services.job_service import JobService

router = APIRouter(prefix="/internal/snapshot-jobs", dependencies=[Depends(require_internal_token)])


@router.post("", response_model=SnapshotJobCreateResponse)
def create_snapshot_job(payload: SnapshotJobCreate, db: Session = Depends(get_db)):
    job = JobService(db).create_job(payload)
    return SnapshotJobCreateResponse(job_id=job.id, status=job.status)


@router.post("/{job_id}/retry-failed", response_model=SnapshotJobCreateResponse)
def retry_failed_chains(job_id: int, db: Session = Depends(get_db)):
    job = JobService(db).create_retry_failed_job(job_id)
    return SnapshotJobCreateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=SnapshotJobStatusResponse)
def get_snapshot_job(job_id: int, db: Session = Depends(get_db)):
    job = JobService(db).get_job(job_id)
    return SnapshotJobStatusResponse(
        job_id=job.id,
        user_id=job.user_id,
        trigger_type=job.trigger_type,
        scope_type=job.scope_type,
        status=job.status,
        group_id=job.group_id,
        wallet_id=job.wallet_id,
        parent_run_id=job.parent_run_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
    )
