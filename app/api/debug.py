from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.auth import require_internal_token
from app.config import get_settings
from app.db import get_db
from app.models.snapshots import BalanceSnapshot, ChainSnapshot, SnapshotRun
from app.schemas.debug import DebugEvmBalanceResponse
from app.schemas.debug import (
    DebugChainItem,
    DebugJobDetail,
    DebugJobItem,
    DebugJobsResponse,
    DebugWalletItem,
)
from app.services.chain_config import SUPPORTED_CHAINS, get_chain_configs
from app.services.evm_collector import EvmCollector
from app.services.price_service import PriceService

router = APIRouter(prefix="/debug")


def require_debug_enabled() -> None:
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="debug endpoints disabled")


@router.get("/jobs", response_model=DebugJobsResponse, dependencies=[Depends(require_debug_enabled)])
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(SnapshotRun).order_by(SnapshotRun.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(SnapshotRun.status == status)
    if user_id:
        stmt = stmt.where(SnapshotRun.user_id == user_id)
    return DebugJobsResponse(items=list(db.scalars(stmt)))


@router.get(
    "/jobs/{job_id}", response_model=DebugJobDetail, dependencies=[Depends(require_debug_enabled)]
)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.scalar(
        select(SnapshotRun)
        .where(SnapshotRun.id == job_id)
        .options(selectinload(SnapshotRun.wallet_snapshots).selectinload("*"))
    )
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    count_stmt = (
        select(BalanceSnapshot.chain_snapshot_id, func.count(BalanceSnapshot.id))
        .join(ChainSnapshot)
        .where(ChainSnapshot.wallet_snapshot_id.in_([w.id for w in job.wallet_snapshots] or [0]))
        .group_by(BalanceSnapshot.chain_snapshot_id)
    )
    balance_counts = dict(db.execute(count_stmt).all())
    wallets = [
        DebugWalletItem(
            id=wallet.id,
            wallet_id=wallet.wallet_id,
            group_id=wallet.group_id,
            wallet_type=wallet.wallet_type,
            status=wallet.status,
            total_usd=wallet.total_usd,
            error_message=wallet.error_message,
            chains=[
                DebugChainItem(
                    id=chain.id,
                    chain=chain.chain,
                    status=chain.status,
                    total_usd=chain.total_usd,
                    rpc_latency_ms=chain.rpc_latency_ms,
                    error_type=chain.error_type,
                    error_message=chain.error_message,
                    balances_count=balance_counts.get(chain.id, 0),
                )
                for chain in wallet.chain_snapshots
            ],
        )
        for wallet in job.wallet_snapshots
    ]
    return DebugJobDetail(job=DebugJobItem.model_validate(job), wallets=wallets)


@router.get(
    "/evm-balance",
    response_model=DebugEvmBalanceResponse,
    dependencies=[Depends(require_debug_enabled), Depends(require_internal_token)],
)
def debug_evm_balance(
    chain: str = Query(..., description=f"One of: {', '.join(SUPPORTED_CHAINS)}"),
    address: str = Query(..., description="EVM wallet address"),
):
    settings = get_settings()
    collector = EvmCollector(get_chain_configs(settings), PriceService(settings))
    result = collector.collect_chain(address=address, chain=chain)
    return DebugEvmBalanceResponse(
        chain=result.chain,
        address=address,
        status=result.status,
        native_balance=result.native_balance,
        total_usd=result.total_usd,
        rpc_latency_ms=result.rpc_latency_ms,
        balances=result.balances,
        error_type=result.error_type,
        error_message=result.error_message,
    )
