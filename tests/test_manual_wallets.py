from datetime import UTC, datetime

from app.enums import JobStatus, ScopeType, TriggerType
from app.models.snapshots import BalanceSnapshot, SnapshotRun, WalletSnapshot
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

