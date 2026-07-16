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
        wallets = list(self.db.scalars(stmt.order_by(Wallet.id)))
        if job.scope_type in (ScopeType.ALL.value, ScopeType.GROUP.value):
            return self._deduplicate_evm_addresses(wallets)
        return wallets

    @staticmethod
    def _deduplicate_evm_addresses(wallets: list[Wallet]) -> list[Wallet]:
        """Keep the oldest active wallet for each case-insensitive EVM address.

        Scheduled and group-wide jobs must not scan the same on-chain address
        more than once. Explicit wallet jobs are intentionally left untouched
        so an existing duplicate record can still be refreshed and inspected.
        """
        seen_addresses: set[str] = set()
        result: list[Wallet] = []
        for wallet in wallets:
            if wallet.wallet_type != "evm" or not wallet.address:
                result.append(wallet)
                continue
            normalized = wallet.address.strip().lower()
            if normalized in seen_addresses:
                continue
            seen_addresses.add(normalized)
            result.append(wallet)
        return result
