import logging
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import ChainStatus, JobStatus, ScopeType, WalletSnapshotStatus, WalletType
from app.metrics import (
    balance_snapshots_written_total,
    chain_duration_seconds,
    chain_last_success_timestamp_seconds,
    chain_requests_total,
    job_duration_seconds,
    jobs_total,
    last_job_completion_timestamp_seconds,
    last_job_success_timestamp_seconds,
    last_success_timestamp,
    rpc_latency_seconds,
    wallets_processed_total,
)
from app.models.external import Wallet
from app.models.snapshots import BalanceSnapshot, ChainSnapshot, SnapshotRun, WalletSnapshot
from app.services.chain_config import get_chain_configs, get_enabled_chains
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
        self.evm_collector = evm_collector or EvmCollector(
            get_chain_configs(settings),
            price_service,
            cooldown_seconds=settings.rpc_cooldown_seconds,
        )
        self.manual_collector = manual_collector or ManualCollector(db, price_service)
        self.wallet_loader = WalletLoader(db)
        self.enabled_chains = get_enabled_chains(settings)

    def process(self, job: SnapshotRun) -> str:
        started = perf_counter()
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
            last_job_completion_timestamp_seconds.labels(job.status, job.trigger_type).set(
                job.finished_at.timestamp()
            )
            job_duration_seconds.labels(job.status, job.trigger_type, job.scope_type).observe(
                perf_counter() - started
            )
            return job.status

        wallet_statuses = [self._process_wallet(job, wallet) for wallet in wallets]
        if all(status == WalletSnapshotStatus.SUCCESS.value for status in wallet_statuses):
            job.status = JobStatus.SUCCESS.value
        elif any(
            status
            in {WalletSnapshotStatus.SUCCESS.value, WalletSnapshotStatus.PARTIAL_SUCCESS.value}
            for status in wallet_statuses
        ):
            job.status = JobStatus.PARTIAL_SUCCESS.value
        else:
            job.status = JobStatus.FAILED.value

        job.finished_at = datetime.now(UTC)
        self.db.commit()
        last_job_completion_timestamp_seconds.labels(job.status, job.trigger_type).set(
            job.finished_at.timestamp()
        )
        if job.status == JobStatus.SUCCESS.value:
            last_success_timestamp.set(job.finished_at.timestamp())
            last_job_success_timestamp_seconds.labels(job.trigger_type, job.scope_type).set(
                job.finished_at.timestamp()
            )
        jobs_total.labels(job.status, job.trigger_type, job.scope_type).inc()
        job_duration_seconds.labels(job.status, job.trigger_type, job.scope_type).observe(
            perf_counter() - started
        )
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
            results = [self._collect_manual_wallet(job, wallet)]
        elif wallet.wallet_type == WalletType.EVM.value:
            chains = self._chains_for_wallet(job, wallet)
            results = [self._collect_evm_chain(job, wallet, chain) for chain in chains]
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

    def _chains_for_wallet(self, job: SnapshotRun, wallet: Wallet) -> tuple[str, ...]:
        if job.scope_type != ScopeType.FAILED_CHAINS.value or job.parent_run_id is None:
            return self.enabled_chains

        stmt = (
            select(ChainSnapshot.chain)
            .join(ChainSnapshot.wallet_snapshot)
            .where(
                WalletSnapshot.snapshot_run_id == job.parent_run_id,
                WalletSnapshot.wallet_id == wallet.id,
                ChainSnapshot.status == ChainStatus.FAILED.value,
            )
            .order_by(ChainSnapshot.chain)
        )
        chains = tuple(chain for chain in self.db.scalars(stmt) if chain in self.enabled_chains)
        return chains or self.enabled_chains

    def _collect_manual_wallet(self, job: SnapshotRun, wallet: Wallet) -> ChainCollectionResult:
        started = perf_counter()
        result = self.manual_collector.collect_wallet(wallet.id)
        chain_duration_seconds.labels(result.chain, result.status).observe(perf_counter() - started)
        logger.info(
            "chain_collection_succeeded"
            if result.status == ChainStatus.SUCCESS.value
            else "chain_collection_failed",
            extra=self._log_extra(
                job,
                wallet_id=wallet.id,
                chain=result.chain,
                status=result.status,
                error_type=result.error_type,
            ),
        )
        return result

    def _collect_evm_chain(
        self, job: SnapshotRun, wallet: Wallet, chain: str
    ) -> ChainCollectionResult:
        logger.info(
            "chain_collection_started",
            extra=self._log_extra(
                job,
                wallet_id=wallet.id,
                chain=chain,
                status=WalletSnapshotStatus.RUNNING.value,
            ),
        )
        started = perf_counter()
        result = self.evm_collector.collect_chain(wallet.address or "", chain)
        chain_duration_seconds.labels(result.chain, result.status).observe(perf_counter() - started)
        if result.rpc_latency_ms is not None:
            rpc_latency_seconds.labels(result.chain).observe(result.rpc_latency_ms / 1000)
        logger.info(
            "chain_collection_succeeded"
            if result.status == ChainStatus.SUCCESS.value
            else "chain_collection_failed",
            extra=self._log_extra(
                job,
                wallet_id=wallet.id,
                chain=result.chain,
                status=result.status,
                error_type=result.error_type,
            ),
        )
        return result

    def _write_chain_result(
        self, wallet_snapshot: WalletSnapshot, result: ChainCollectionResult
    ) -> None:
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
        chain_requests_total.labels(result.chain, result.status, result.error_type or "none").inc()
        if result.status == ChainStatus.SUCCESS.value:
            chain_last_success_timestamp_seconds.labels(result.chain).set(now.timestamp())
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
