from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ScopeType
from app.models.external import Wallet
from app.models.snapshots import SnapshotRun


class WalletLoader:
    def __init__(self, db: Session):
        self.db = db

    def load_for_job(self, job: SnapshotRun) -> list[Wallet]:
        stmt = select(Wallet).where(Wallet.user_id == job.user_id, Wallet.is_active.is_(True))
        if job.scope_type == ScopeType.GROUP.value:
            stmt = stmt.where(Wallet.group_id == job.group_id)
        elif job.scope_type == ScopeType.WALLET.value:
            stmt = stmt.where(Wallet.id == job.wallet_id)
        elif job.scope_type == ScopeType.FAILED_CHAINS.value:
            # Chain-level narrowing happens in SnapshotProcessor using parent_run_id.
            if job.wallet_id:
                stmt = stmt.where(Wallet.id == job.wallet_id)
            elif job.group_id:
                stmt = stmt.where(Wallet.group_id == job.group_id)
        return list(self.db.scalars(stmt.order_by(Wallet.id)))
