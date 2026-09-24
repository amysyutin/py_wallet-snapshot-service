from app.enums import ChainStatus, JobStatus, ScopeType, TriggerType
from app.models.external import User, Wallet
from app.models.snapshots import ChainSnapshot, SnapshotRun, WalletSnapshot
from app.services.wallet_loader import WalletLoader


def _job(
    db_session,
    *,
    scope_type: str,
    wallet_id: int | None = None,
    group_id: int | None = None,
    parent_run_id: int | None = None,
):
    job = SnapshotRun(
        user_id=1,
        trigger_type=TriggerType.MANUAL.value,
        scope_type=scope_type,
        group_id=group_id,
        wallet_id=wallet_id,
        parent_run_id=parent_run_id,
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _add_chain_snapshot(
    db_session,
    *,
    run_id: int,
    wallet_id: int,
    status: str,
):
    wallet_snapshot = WalletSnapshot(
        snapshot_run_id=run_id,
        wallet_id=wallet_id,
        group_id=10,
        wallet_type="evm",
        status=status,
    )
    wallet_snapshot.chain_snapshots.append(ChainSnapshot(chain="mainnet", status=status))
    db_session.add(wallet_snapshot)


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


def test_all_scope_deduplicates_exact_solana_addresses_but_preserves_case(db_session):
    address = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    case_variant = "ePjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    db_session.add(User(id=1, email="solana-dedupe@example.test"))
    db_session.add_all(
        [
            Wallet(
                id=1,
                user_id=1,
                group_id=10,
                label="Canonical",
                address=address,
                chain_type="solana",
                wallet_type="solana",
                is_active=True,
            ),
            Wallet(
                id=2,
                user_id=1,
                group_id=10,
                label="Duplicate",
                address=address,
                chain_type="solana",
                wallet_type="solana",
                is_active=True,
            ),
            Wallet(
                id=3,
                user_id=1,
                group_id=10,
                label="Different base58 address",
                address=case_variant,
                chain_type="solana",
                wallet_type="solana",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    wallets = WalletLoader(db_session).load_for_job(
        _job(db_session, scope_type=ScopeType.ALL.value)
    )

    assert [wallet.id for wallet in wallets] == [1, 3]


def test_group_scope_filters_owner_group_and_active_wallets_before_deduplication(
    db_session,
):
    db_session.add_all(
        [
            User(id=1, email="group-owner@example.test"),
            User(id=2, email="group-other@example.test"),
        ]
    )
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
                group_id=20,
                label="Other group",
                address="0x0000000000000000000000000000000000000003",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=4,
                user_id=1,
                group_id=10,
                label="Inactive",
                address="0x0000000000000000000000000000000000000004",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=False,
            ),
            Wallet(
                id=5,
                user_id=2,
                group_id=10,
                label="Other user",
                address="0x0000000000000000000000000000000000000005",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=6,
                user_id=1,
                group_id=10,
                label="Manual",
                address=None,
                chain_type=None,
                wallet_type="manual",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    wallets = WalletLoader(db_session).load_for_job(
        _job(
            db_session,
            scope_type=ScopeType.GROUP.value,
            group_id=10,
        )
    )

    assert [wallet.id for wallet in wallets] == [1, 6]


def test_failed_chains_scope_filters_parent_status_owner_and_active_wallets(
    db_session,
):
    db_session.add_all(
        [
            User(id=1, email="retry-owner@example.test"),
            User(id=2, email="retry-other@example.test"),
        ]
    )
    db_session.add_all(
        [
            Wallet(
                id=1,
                user_id=1,
                group_id=10,
                label="Failed",
                address="0x00000000000000000000000000000000000000Aa",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=2,
                user_id=1,
                group_id=10,
                label="Failed duplicate",
                address=" 0x00000000000000000000000000000000000000aa ",
                chain_type="base",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=3,
                user_id=1,
                group_id=10,
                label="Succeeded",
                address="0x0000000000000000000000000000000000000003",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=4,
                user_id=1,
                group_id=10,
                label="Failed in other run",
                address="0x0000000000000000000000000000000000000004",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
            Wallet(
                id=5,
                user_id=1,
                group_id=10,
                label="Inactive failure",
                address="0x0000000000000000000000000000000000000005",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=False,
            ),
            Wallet(
                id=6,
                user_id=2,
                group_id=10,
                label="Other owner failure",
                address="0x0000000000000000000000000000000000000006",
                chain_type="mainnet",
                wallet_type="evm",
                is_active=True,
            ),
        ]
    )
    db_session.commit()
    parent_job = _job(db_session, scope_type=ScopeType.ALL.value)
    other_parent_job = _job(db_session, scope_type=ScopeType.ALL.value)
    for wallet_id in (1, 2, 5, 6):
        _add_chain_snapshot(
            db_session,
            run_id=parent_job.id,
            wallet_id=wallet_id,
            status=ChainStatus.FAILED.value,
        )
    _add_chain_snapshot(
        db_session,
        run_id=parent_job.id,
        wallet_id=3,
        status=ChainStatus.SUCCESS.value,
    )
    _add_chain_snapshot(
        db_session,
        run_id=other_parent_job.id,
        wallet_id=4,
        status=ChainStatus.FAILED.value,
    )
    db_session.commit()

    wallets = WalletLoader(db_session).load_for_job(
        _job(
            db_session,
            scope_type=ScopeType.FAILED_CHAINS.value,
            parent_run_id=parent_job.id,
        )
    )

    assert [wallet.id for wallet in wallets] == [1]
