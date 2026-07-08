from datetime import UTC, datetime
from decimal import Decimal

from app.enums import AssetType, ChainStatus, JobStatus, ScopeType, TriggerType
from app.models.snapshots import SnapshotRun
from app.services.evm_collector import AssetBalance, ChainCollectionResult
from app.services.snapshot_processor import SnapshotProcessor
from tests.conftest import seed_user_wallet


class FakeEvmCollector:
    def __init__(self, statuses):
        self.statuses = statuses

    def collect_chain(self, address, chain):
        status = self.statuses.get(chain, ChainStatus.SUCCESS.value)
        if status == ChainStatus.SUCCESS.value:
            return ChainCollectionResult(
                chain=chain,
                status=status,
                native_balance=Decimal("1"),
                total_usd=Decimal("10"),
                rpc_latency_ms=1,
                balances=[
                    AssetBalance(
                        symbol="ETH",
                        asset_address=None,
                        asset_type=AssetType.NATIVE.value,
                        amount=Decimal("1"),
                        price_usd=Decimal("10"),
                        value_usd=Decimal("10"),
                        price_source="test",
                    )
                ],
            )
        return ChainCollectionResult(
            chain=chain,
            status=ChainStatus.FAILED.value,
            native_balance=None,
            total_usd=Decimal("0"),
            rpc_latency_ms=None,
            balances=[],
            error_type="timeout",
            error_message="timeout",
        )


def make_job(db_session):
    seed_user_wallet(
        db_session,
        wallet_type="evm",
        address="0x0000000000000000000000000000000000000001",
    )
    job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.MANUAL.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_one_failed_chain_is_partial_success(db_session):
    job = make_job(db_session)
    status = SnapshotProcessor(
        db_session,
        evm_collector=FakeEvmCollector({"mainnet": ChainStatus.FAILED.value}),
    ).process(job)

    assert status == JobStatus.PARTIAL_SUCCESS.value


def test_all_failed_chains_fail_job(db_session):
    job = make_job(db_session)
    status = SnapshotProcessor(
        db_session,
        evm_collector=FakeEvmCollector(
            {chain: ChainStatus.FAILED.value for chain in ["mainnet", "base", "arbitrum", "bnb", "linea"]}
        ),
    ).process(job)

    assert status == JobStatus.FAILED.value


def test_all_successful_chains_succeed_job(db_session):
    job = make_job(db_session)
    status = SnapshotProcessor(db_session, evm_collector=FakeEvmCollector({})).process(job)

    assert status == JobStatus.SUCCESS.value
