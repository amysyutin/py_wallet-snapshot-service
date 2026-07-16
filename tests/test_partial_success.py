from datetime import UTC, datetime
from decimal import Decimal

from app.config import get_settings
from app.enums import AssetType, ChainStatus, JobStatus, ScopeType, TriggerType
from app.models.snapshots import BalanceSnapshot, SnapshotRun
from app.services.evm_collector import AssetBalance, ChainCollectionResult
from app.services.snapshot_processor import SnapshotProcessor
from tests.conftest import seed_user_wallet


class FakeEvmCollector:
    def __init__(self, statuses):
        self.statuses = statuses
        self.calls = []

    def collect_chain(self, address, chain):
        self.calls.append(chain)
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


class TokenEvmCollector(FakeEvmCollector):
    def collect_chain(self, address, chain):
        result = super().collect_chain(address, chain)
        result.balances.append(
            AssetBalance(
                symbol="USDC",
                asset_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                asset_type=AssetType.ERC20.value,
                amount=Decimal("12.5"),
                price_usd=Decimal("1"),
                value_usd=Decimal("12.5"),
                price_source="test",
            )
        )
        result.total_usd += Decimal("12.5")
        return result


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
            {
                chain: ChainStatus.FAILED.value
                for chain in ["mainnet", "base", "arbitrum", "bnb", "linea"]
            }
        ),
    ).process(job)

    assert status == JobStatus.FAILED.value


def test_all_successful_chains_succeed_job(db_session):
    job = make_job(db_session)
    status = SnapshotProcessor(db_session, evm_collector=FakeEvmCollector({})).process(job)

    assert status == JobStatus.SUCCESS.value


def test_erc20_balances_are_persisted(db_session, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_ENABLED_CHAINS", "base")
    get_settings.cache_clear()
    job = make_job(db_session)

    try:
        status = SnapshotProcessor(
            db_session,
            evm_collector=TokenEvmCollector({}),
        ).process(job)
    finally:
        get_settings.cache_clear()

    token = db_session.query(BalanceSnapshot).filter_by(asset_symbol="USDC").one()
    assert status == JobStatus.SUCCESS.value
    assert token.asset_type == AssetType.ERC20.value
    assert token.amount == Decimal("12.5")
    assert token.value_usd == Decimal("12.5")


def test_enabled_chains_limits_evm_collection(db_session, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_ENABLED_CHAINS", "mainnet")
    get_settings.cache_clear()
    job = make_job(db_session)
    collector = FakeEvmCollector({})

    try:
        status = SnapshotProcessor(db_session, evm_collector=collector).process(job)
    finally:
        get_settings.cache_clear()

    assert status == JobStatus.SUCCESS.value
    assert collector.calls == ["mainnet"]


def test_retry_failed_chains_collects_only_failed_parent_chains(db_session):
    parent_job = make_job(db_session)
    parent_collector = FakeEvmCollector({"mainnet": ChainStatus.FAILED.value})
    SnapshotProcessor(db_session, evm_collector=parent_collector).process(parent_job)

    retry_job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.RETRY.value,
        scope_type=ScopeType.FAILED_CHAINS.value,
        status=JobStatus.RUNNING.value,
        parent_run_id=parent_job.id,
        created_at=datetime.now(UTC),
    )
    db_session.add(retry_job)
    db_session.commit()
    retry_collector = FakeEvmCollector({})

    status = SnapshotProcessor(db_session, evm_collector=retry_collector).process(retry_job)

    assert status == JobStatus.SUCCESS.value
    assert retry_collector.calls == ["mainnet"]
