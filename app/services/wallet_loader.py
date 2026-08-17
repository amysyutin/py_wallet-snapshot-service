from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ScopeType
from app.models.external import Wallet
from app.models.snapshots import ChainSnapshot, SnapshotRun, WalletSnapshot


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
            stmt = (
                stmt.join(WalletSnapshot, WalletSnapshot.wallet_id == Wallet.id)
                .join(
                    ChainSnapshot,
                    ChainSnapshot.wallet_snapshot_id == WalletSnapshot.id,
                )
                .where(
                    WalletSnapshot.snapshot_run_id == job.parent_run_id,
                    ChainSnapshot.status == "failed",
                )
                .distinct()
            )
        wallets = list(self.db.scalars(stmt.order_by(Wallet.id)))
        if job.scope_type in (
            ScopeType.ALL.value,
            ScopeType.GROUP.value,
            ScopeType.FAILED_CHAINS.value,
        ):
            return self._deduplicate_onchain_addresses(wallets)
        return wallets

    @staticmethod
    def _deduplicate_onchain_addresses(wallets: list[Wallet]) -> list[Wallet]:
        """Keep the oldest active wallet for each normalized on-chain address.

        Scheduled and group-wide jobs must not scan the same on-chain address
        more than once. Explicit wallet jobs are intentionally left untouched
        so an existing duplicate record can still be refreshed and inspected.
        EVM addresses are case-insensitive here; Solana base58 addresses are not.
        """
        seen_addresses: set[tuple[str, str]] = set()
        result: list[Wallet] = []
        for wallet in wallets:
            if wallet.wallet_type not in {"evm", "solana"} or not wallet.address:
                result.append(wallet)
                continue
            normalized = wallet.address.strip()
            if wallet.wallet_type == "evm":
                normalized = normalized.lower()
            address_key = (wallet.wallet_type, normalized)
            if address_key in seen_addresses:
                continue
            seen_addresses.add(address_key)
            result.append(wallet)
        return result
