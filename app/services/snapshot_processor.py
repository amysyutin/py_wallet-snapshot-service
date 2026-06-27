import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import ChainStatus, JobStatus, WalletSnapshotStatus, WalletType
from app.metrics import (
    balance_snapshots_written_total,
    chain_requests_total,
    jobs_total,
    last_success_timestamp,
    wallets_processed_total,
)
from app.models.external import Wallet
from app.models.snapshots import BalanceSnapshot, ChainSnapshot, SnapshotRun, WalletSnapshot
from app.services.chain_config import SUPPORTED_CHAINS, get_chain_configs
from app.services.evm_collector import ChainCollectionResult, EvmCollector
from app.services.manual_collector import ManualCollector
from app.services.price_service import PriceService
from app.services.wallet_loader import WalletLoader

logger = logging.getLogger(__name__)


class SnapshotProcessor:
    def __init__(
        self,
        db: Session,
        evm_collector: EvmCollector | None = None,
        manual_collector: ManualCollector | None = None,
    ):
        self.db = db
        settings = get_settings()
        price_service = PriceService(settings)
        self.evm_collector = evm_collector or EvmCollector(get_chain_configs(settings), price_service)
        self.manual_collector = manual_collector or ManualCollector(db, price_service)
        self.wallet_loader = WalletLoader(db)

    def process(self, job: SnapshotRun) -> str:
        logger.info(
            "snapshot_job_started",
            extra=self._log_extra(job, status=JobStatus.RUNNING.value),
        )
        wallets = self.wallet_loader.load_for_job(job)
        if not wallets:
            job.status = JobStatus.FAILED.value
            job.error_message = "no active wallets found for job scope"
            job.finished_at = datetime.now(UTC)
            self.db.commit()
            jobs_total.labels(job.status, job.trigger_type, job.scope_type).inc()
            return job.status

        wallet_statuses = [self._process_wallet(job, wallet) for wallet in wallets]
        if all(status == WalletSnapshotStatus.SUCCESS.value for status in wallet_statuses):
            job.status = JobStatus.SUCCESS.value
            last_success_timestamp.set(datetime.now(UTC).timestamp())
        elif any(
            status in {WalletSnapshotStatus.SUCCESS.value, WalletSnapshotStatus.PARTIAL_SUCCESS.value}
            for status in wallet_statuses
        ):
            job.status = JobStatus.PARTIAL_SUCCESS.value
        else:
            job.status = JobStatus.FAILED.value

        job.finished_at = datetime.now(UTC)
        self.db.commit()
        jobs_total.labels(job.status, job.trigger_type, job.scope_type).inc()
        logger.info("snapshot_job_finished", extra=self._log_extra(job, status=job.status))
        return job.status

    def _process_wallet(self, job: SnapshotRun, wallet: Wallet) -> str:
        started_at = datetime.now(UTC)
        wallet_snapshot = WalletSnapshot(
            snapshot_run_id=job.id,
            wallet_id=wallet.id,
            group_id=wallet.group_id,
            wallet_type=wallet.wallet_type,
            status=WalletSnapshotStatus.RUNNING.value,
            total_usd=Decimal("0"),
            started_at=started_at,
        )
        self.db.add(wallet_snapshot)
        self.db.flush()
        logger.info(
            "wallet_snapshot_started",
            extra=self._log_extra(job, wallet_id=wallet.id, status=wallet_snapshot.status),
        )

        if wallet.wallet_type == WalletType.MANUAL.value:
            results = [self.manual_collector.collect_wallet(wallet.id)]
        elif wallet.wallet_type == WalletType.EVM.value:
            results = [self.evm_collector.collect_chain(wallet.address or "", chain) for chain in SUPPORTED_CHAINS]
        else:
            results = [
                ChainCollectionResult(
                    chain=wallet.chain_type or "unknown",
                    status=ChainStatus.FAILED.value,
                    native_balance=None,
                    total_usd=Decimal("0"),
                    rpc_latency_ms=None,
                    balances=[],
                    error_type="unsupported_wallet_type",
                    error_message=f"unsupported wallet_type={wallet.wallet_type}",
                )
            ]

        for result in results:
            self._write_chain_result(wallet_snapshot, result)

        statuses = [result.status for result in results]
        wallet_snapshot.total_usd = sum((result.total_usd for result in results), Decimal("0"))
        if all(status == ChainStatus.SUCCESS.value for status in statuses):
            wallet_snapshot.status = WalletSnapshotStatus.SUCCESS.value
        elif any(status == ChainStatus.SUCCESS.value for status in statuses):
            wallet_snapshot.status = WalletSnapshotStatus.PARTIAL_SUCCESS.value
        else:
            wallet_snapshot.status = WalletSnapshotStatus.FAILED.value
            wallet_snapshot.error_message = "all chains failed"
        wallet_snapshot.finished_at = datetime.now(UTC)
        self.db.commit()
        wallets_processed_total.labels(wallet_snapshot.status).inc()
        return wallet_snapshot.status

    def _write_chain_result(self, wallet_snapshot: WalletSnapshot, result: ChainCollectionResult) -> None:
        now = datetime.now(UTC)
        chain_snapshot = ChainSnapshot(
            wallet_snapshot_id=wallet_snapshot.id,
            chain=result.chain,
            status=result.status,
            native_balance=result.native_balance,
            total_usd=result.total_usd,
            rpc_latency_ms=result.rpc_latency_ms,
            error_type=result.error_type,
            error_message=result.error_message,
            started_at=now,
            finished_at=now,
        )
        self.db.add(chain_snapshot)
        self.db.flush()
        chain_requests_total.labels(
            result.chain, result.status, result.error_type or "none"
        ).inc()
        for balance in result.balances:
            self.db.add(
                BalanceSnapshot(
                    chain_snapshot_id=chain_snapshot.id,
                    asset_symbol=balance.symbol,
                    asset_address=balance.asset_address,
                    asset_type=balance.asset_type,
                    amount=balance.amount,
                    price_usd=balance.price_usd,
                    value_usd=balance.value_usd,
                    price_source=balance.price_source,
                )
            )
            balance_snapshots_written_total.inc()

    @staticmethod
    def _log_extra(
        job: SnapshotRun,
        status: str,
        wallet_id: int | None = None,
        chain: str | None = None,
        error_type: str | None = None,
    ) -> dict[str, object]:
        return {
            "job_id": job.id,
            "user_id": job.user_id,
            "trigger_type": job.trigger_type,
            "scope_type": job.scope_type,
            "status": status,
            "wallet_id": wallet_id,
            "chain": chain,
            "error_type": error_type,
        }
