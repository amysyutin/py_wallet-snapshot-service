"""repair snapshot schema drift

Revision ID: 20260710_0002
Revises: 20260628_0001
Create Date: 2026-07-10
"""
from alembic import op

revision = "20260710_0002"
down_revision = "20260628_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The shared dev DB can have 20260628_0001 stamped while still containing
    # the older py_wallet snapshot tables. Use IF NOT EXISTS so fresh DBs that
    # already have the new columns from 0001 can still upgrade to this revision.
    op.execute("ALTER TABLE snapshot_runs ADD COLUMN IF NOT EXISTS group_id BIGINT")
    op.execute("ALTER TABLE snapshot_runs ADD COLUMN IF NOT EXISTS parent_run_id BIGINT")
    op.execute(
        "ALTER TABLE snapshot_runs "
        "ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"
    )

    op.execute("ALTER TABLE wallet_snapshots ADD COLUMN IF NOT EXISTS group_id BIGINT")
    op.execute(
        "ALTER TABLE wallet_snapshots "
        "ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE wallet_snapshots "
        "ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute("ALTER TABLE wallet_snapshots ADD COLUMN IF NOT EXISTS error_message TEXT")

    op.execute(
        "ALTER TABLE chain_snapshots ADD COLUMN IF NOT EXISTS native_balance NUMERIC(38, 18)"
    )
    op.execute("ALTER TABLE chain_snapshots ADD COLUMN IF NOT EXISTS rpc_latency_ms INTEGER")
    op.execute(
        "ALTER TABLE chain_snapshots "
        "ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE chain_snapshots "
        "ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP WITH TIME ZONE"
    )

    op.execute(
        "ALTER TABLE snapshot_balance_snapshots "
        "ADD COLUMN IF NOT EXISTS asset_address VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE snapshot_balance_snapshots "
        "ADD COLUMN IF NOT EXISTS asset_type VARCHAR(32) NOT NULL DEFAULT 'native'"
    )
    op.execute(
        "ALTER TABLE snapshot_balance_snapshots ALTER COLUMN asset_type DROP DEFAULT"
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_runs_trigger_type ON snapshot_runs (trigger_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_runs_scope_type ON snapshot_runs (scope_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_runs_group_id ON snapshot_runs (group_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_runs_wallet_id ON snapshot_runs (wallet_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_runs_parent_run_id "
        "ON snapshot_runs (parent_run_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_runs_created_at ON snapshot_runs (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_runs_user_status_created "
        "ON snapshot_runs (user_id, status, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_runs_status_created "
        "ON snapshot_runs (status, created_at)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_snapshots_snapshot_run_id "
        "ON wallet_snapshots (snapshot_run_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_wallet_snapshots_group_id ON wallet_snapshots (group_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_snapshots_run_wallet "
        "ON wallet_snapshots (snapshot_run_id, wallet_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_snapshots_run_group "
        "ON wallet_snapshots (snapshot_run_id, group_id)"
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_snapshots_chain ON chain_snapshots (chain)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chain_snapshots_error_type "
        "ON chain_snapshots (error_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chain_snapshots_wallet_chain "
        "ON chain_snapshots (wallet_snapshot_id, chain)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_balance_snapshots_asset_symbol "
        "ON snapshot_balance_snapshots (asset_symbol)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_balance_snapshots_chain_symbol "
        "ON snapshot_balance_snapshots (chain_snapshot_id, asset_symbol)"
    )


def downgrade() -> None:
    # Intentionally no-op. This repair revision may run after a clean 0001 where
    # these columns are part of the base schema, so dropping them would corrupt it.
    pass
