from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.enums import AssetType, ChainStatus, JobStatus, ScopeType, TriggerType
from app.models.external import Asset, PriceHistory
from app.models.snapshots import SnapshotRun
from app.services.evm_collector import AssetBalance, ChainCollectionResult
from app.services.price_history import PriceHistoryRecorder
from app.services.snapshot_processor import SnapshotProcessor
from tests.conftest import seed_user_wallet

WBTC_ADDRESS = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"


def _balance(
    *,
    symbol: str = "WBTC",
    address: str | None = WBTC_ADDRESS,
    amount: Decimal = Decimal("1.5"),
    price: Decimal | None = Decimal("78619"),
    source: str | None = "coingecko",
    decimals: int = 8,
) -> AssetBalance:
    return AssetBalance(
        symbol=symbol,
        asset_address=address,
        asset_type=AssetType.ERC20.value,
        amount=amount,
        price_usd=price,
        value_usd=amount * price if price is not None else Decimal("0"),
        price_source=source,
        decimals=decimals,
    )


def test_records_provider_price_once_per_asset_and_job(db_session):
    recorder = PriceHistoryRecorder(db_session)
    observed_at = datetime(2026, 9, 2, 7, 0, tzinfo=UTC)
    recorder.begin_job()

    assert recorder.record(
        chain="MAINNET",
        balance=_balance(),
        observed_at=observed_at,
    )
    assert not recorder.record(
        chain="mainnet",
        balance=_balance(address=f"0X{WBTC_ADDRESS[2:].lower()}"),
        observed_at=observed_at,
    )
    db_session.flush()

    asset = db_session.query(Asset).one()
    price = db_session.query(PriceHistory).one()
    assert asset.symbol == "WBTC"
    assert asset.chain == "mainnet"
    assert asset.contract_address == WBTC_ADDRESS.lower()
    assert asset.decimals == 8
    assert price.asset_id == asset.id
    assert price.price_usd == Decimal("78619")
    assert price.source == "coingecko"


def test_new_job_records_new_observation_for_existing_asset(db_session):
    existing = Asset(
        id=41,
        symbol="WETH",
        name="Wrapped Ether",
        contract_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        chain="mainnet",
        decimals=18,
    )
    db_session.add(existing)
    db_session.commit()
    recorder = PriceHistoryRecorder(db_session)
    first_at = datetime(2026, 9, 2, 7, 0, tzinfo=UTC)
    balance = _balance(
        symbol="WETH",
        address=existing.contract_address.lower(),
        amount=Decimal("2"),
        price=Decimal("2500"),
        decimals=18,
    )

    recorder.begin_job()
    assert recorder.record(chain="mainnet", balance=balance, observed_at=first_at)
    recorder.begin_job()
    assert recorder.record(
        chain="mainnet",
        balance=balance,
        observed_at=first_at + timedelta(minutes=5),
    )
    db_session.flush()

    assert db_session.query(Asset).count() == 1
    assert db_session.query(PriceHistory).count() == 2


def test_records_frankfurter_rate_against_existing_manual_asset(db_session):
    asset = Asset(
        id=42,
        symbol="EUR",
        name="Euro",
        contract_address=None,
        chain="manual",
        decimals=2,
    )
    db_session.add(asset)
    db_session.commit()
    recorder = PriceHistoryRecorder(db_session)
    recorder.begin_job()

    assert recorder.record(
        chain="manual",
        balance=_balance(
            symbol="eur",
            address=None,
            amount=Decimal("125"),
            price=Decimal("1.1641"),
            source="frankfurter",
            decimals=2,
        ),
        observed_at=datetime.now(UTC),
    )
    db_session.flush()

    assert db_session.query(Asset).count() == 1
    history = db_session.query(PriceHistory).one()
    assert history.asset_id == asset.id
    assert history.source == "frankfurter"


def test_skips_non_provider_or_unowned_prices(db_session):
    recorder = PriceHistoryRecorder(db_session)
    observed_at = datetime.now(UTC)
    recorder.begin_job()

    for balance in (
        _balance(source="manual"),
        _balance(source="static_dev"),
        _balance(source=None),
        _balance(price=None),
        _balance(price=Decimal("0")),
        _balance(amount=Decimal("0")),
    ):
        assert not recorder.record(
            chain="mainnet",
            balance=balance,
            observed_at=observed_at,
        )

    assert db_session.query(Asset).count() == 0
    assert db_session.query(PriceHistory).count() == 0


class ProviderPriceCollector:
    @staticmethod
    def collect_chain(_address: str, chain: str) -> ChainCollectionResult:
        balance = _balance(
            symbol="ETH",
            address=None,
            amount=Decimal("2"),
            price=Decimal("2500"),
            decimals=18,
        )
        balance.asset_type = AssetType.NATIVE.value
        return ChainCollectionResult(
            chain=chain,
            status=ChainStatus.SUCCESS.value,
            native_balance=balance.amount,
            total_usd=balance.value_usd,
            rpc_latency_ms=1,
            balances=[balance],
        )


def test_snapshot_processor_records_observed_provider_price(db_session):
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
    processor = SnapshotProcessor(db_session, evm_collector=ProviderPriceCollector())
    processor.enabled_chains = ("mainnet",)

    assert processor.process(job) == JobStatus.SUCCESS.value

    asset = db_session.query(Asset).one()
    history = db_session.query(PriceHistory).one()
    assert asset.symbol == "ETH"
    assert asset.contract_address is None
    assert history.price_usd == Decimal("2500")
    assert history.source == "coingecko"
