from datetime import UTC, datetime
from decimal import Decimal

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.external import ManualBalance
from app.models.snapshots import BalanceSnapshot, SnapshotRun, WalletSnapshot
from app.services.manual_collector import ManualCollector
from app.services.snapshot_processor import SnapshotProcessor
from tests.conftest import seed_manual_balance, seed_user_wallet


def test_manual_wallet_creates_snapshots(db_session):
    seed_user_wallet(db_session, wallet_type="manual")
    seed_manual_balance(db_session)
    job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.MANUAL.value,
        scope_type=ScopeType.ALL.value,
        status=JobStatus.RUNNING.value,
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()

    status = SnapshotProcessor(db_session).process(job)

    assert status == JobStatus.SUCCESS.value
    wallet_snapshot = db_session.query(WalletSnapshot).one()
    assert str(wallet_snapshot.total_usd) == "12.500000000000000000"
    assert db_session.query(BalanceSnapshot).count() == 1


def test_manual_wallet_resolves_blank_price_from_ticker(db_session):
    class FiatPriceService:
        def get_usd_price(self, symbol: str):
            assert symbol == "EUR"
            return Decimal("1.2"), "frankfurter"

    seed_user_wallet(db_session, wallet_type="manual")
    seed_manual_balance(db_session, symbol="EUR")
    manual_balance = db_session.query(ManualBalance).one()
    manual_balance.price_usd = None
    db_session.commit()

    result = ManualCollector(db_session, FiatPriceService()).collect_wallet(1)

    assert result.status == "success"
    assert result.total_usd == Decimal("15")
    assert len(result.balances) == 1
    assert result.balances[0].price_usd == Decimal("1.2")
    assert result.balances[0].price_source == "frankfurter"


def test_manual_wallet_explicit_price_overrides_live_ticker(db_session):
    class UnexpectedPriceService:
        def get_usd_price(self, _symbol: str):
            raise AssertionError("explicit manual price must not call live providers")

    seed_user_wallet(db_session, wallet_type="manual")
    seed_manual_balance(db_session, symbol="EUR")

    result = ManualCollector(db_session, UnexpectedPriceService()).collect_wallet(1)

    assert result.status == "success"
    assert result.total_usd == Decimal("12.5")
    assert result.balances[0].price_source == "manual"
