from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import require_internal_token
from app.db import get_db
from app.schemas.jobs import SnapshotJobCreate, SnapshotJobCreateResponse
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

