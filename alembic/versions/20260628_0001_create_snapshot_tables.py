"""create snapshot tables

Revision ID: 20260628_0001
Revises:
Create Date: 2026-06-28
"""

import sqlalchemy as sa

from alembic import op

revision = "20260628_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "snapshot_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("wallet_id", sa.Integer(), nullable=True),
        sa.Column("parent_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_snapshot_runs_user_id", "snapshot_runs", ["user_id"])
    op.create_index("ix_snapshot_runs_trigger_type", "snapshot_runs", ["trigger_type"])
    op.create_index("ix_snapshot_runs_scope_type", "snapshot_runs", ["scope_type"])
    op.create_index("ix_snapshot_runs_group_id", "snapshot_runs", ["group_id"])
    op.create_index("ix_snapshot_runs_wallet_id", "snapshot_runs", ["wallet_id"])
    op.create_index("ix_snapshot_runs_parent_run_id", "snapshot_runs", ["parent_run_id"])
    op.create_index("ix_snapshot_runs_status", "snapshot_runs", ["status"])
    op.create_index("ix_snapshot_runs_created_at", "snapshot_runs", ["created_at"])
    op.create_index(
        "ix_snapshot_runs_user_status_created",
        "snapshot_runs",
        ["user_id", "status", "created_at"],
    )
    op.create_index("ix_snapshot_runs_status_created", "snapshot_runs", ["status", "created_at"])

    op.create_table(
        "wallet_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_run_id", sa.Integer(), sa.ForeignKey("snapshot_runs.id"), nullable=False
        ),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("wallet_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_wallet_snapshots_snapshot_run_id", "wallet_snapshots", ["snapshot_run_id"])
    op.create_index("ix_wallet_snapshots_wallet_id", "wallet_snapshots", ["wallet_id"])
    op.create_index("ix_wallet_snapshots_group_id", "wallet_snapshots", ["group_id"])
    op.create_index("ix_wallet_snapshots_status", "wallet_snapshots", ["status"])
    op.create_index(
        "ix_wallet_snapshots_run_wallet", "wallet_snapshots", ["snapshot_run_id", "wallet_id"]
    )
    op.create_index(
        "ix_wallet_snapshots_run_group", "wallet_snapshots", ["snapshot_run_id", "group_id"]
    )

    op.create_table(
        "chain_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "wallet_snapshot_id", sa.Integer(), sa.ForeignKey("wallet_snapshots.id"), nullable=False
        ),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("native_balance", sa.Numeric(38, 18), nullable=True),
        sa.Column("total_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("rpc_latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chain_snapshots_wallet_snapshot_id", "chain_snapshots", ["wallet_snapshot_id"]
    )
    op.create_index("ix_chain_snapshots_chain", "chain_snapshots", ["chain"])
    op.create_index("ix_chain_snapshots_status", "chain_snapshots", ["status"])
    op.create_index("ix_chain_snapshots_error_type", "chain_snapshots", ["error_type"])
    op.create_index(
        "ix_chain_snapshots_wallet_chain", "chain_snapshots", ["wallet_snapshot_id", "chain"]
    )

    op.create_table(
        "snapshot_balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chain_snapshot_id", sa.Integer(), sa.ForeignKey("chain_snapshots.id"), nullable=False
        ),
        sa.Column("asset_symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_address", sa.String(length=255), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("price_usd", sa.Numeric(38, 18), nullable=True),
        sa.Column("value_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("price_source", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_snapshot_balance_snapshots_chain_snapshot_id",
        "snapshot_balance_snapshots",
        ["chain_snapshot_id"],
    )
    op.create_index(
        "ix_snapshot_balance_snapshots_asset_symbol",
        "snapshot_balance_snapshots",
        ["asset_symbol"],
    )
    op.create_index(
        "ix_snapshot_balance_snapshots_chain_symbol",
        "snapshot_balance_snapshots",
        ["chain_snapshot_id", "asset_symbol"],
    )


def downgrade() -> None:
    op.drop_table("snapshot_balance_snapshots")
    op.drop_table("chain_snapshots")
    op.drop_table("wallet_snapshots")
    op.drop_table("snapshot_runs")
