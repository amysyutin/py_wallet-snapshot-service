from app.enums import JobStatus, ScopeType, TriggerType
from app.models.external import User, Wallet
from app.models.snapshots import SnapshotRun
from app.services.wallet_loader import WalletLoader


def _job(db_session, *, scope_type: str, wallet_id: int | None = None):
    job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.MANUAL.value,
        scope_type=scope_type,
        group_id=None,
        wallet_id=wallet_id,
        parent_run_id=None,
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_all_scope_deduplicates_case_insensitive_evm_addresses(db_session):
    db_session.add(User(id=1, email="dedupe@example.test"))
    db_session.add_all(
        [
            Wallet(
                id=1,
                user_id=1,
                group_id=10,
                label="Canonical",
                address="0x00000000000000000000000000000000000000Aa",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=2,
                user_id=1,
                group_id=10,
                label="Duplicate",
                address=" 0x00000000000000000000000000000000000000aa ",
                chain_type="base",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=3,
                user_id=1,
                group_id=10,
                label="Manual",
                address=None,
                chain_type="manual",
                wallet_type="manual",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    wallets = WalletLoader(db_session).load_for_job(
        _job(db_session, scope_type=ScopeType.ALL.value)
    )

    assert [wallet.id for wallet in wallets] == [1, 3]


def test_wallet_scope_keeps_explicit_duplicate_record(db_session):
    db_session.add(User(id=1, email="explicit@example.test"))
    db_session.add_all(
        [
            Wallet(
                id=1,
                user_id=1,
                group_id=10,
                label="Canonical",
                address="0x00000000000000000000000000000000000000aa",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=2,
                user_id=1,
                group_id=10,
                label="Duplicate",
                address="0x00000000000000000000000000000000000000AA",
                chain_type="base",
                wallet_type="evm",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    wallets = WalletLoader(db_session).load_for_job(
        _job(db_session, scope_type=ScopeType.WALLET.value, wallet_id=2)
    )

    assert [wallet.id for wallet in wallets] == [2]
