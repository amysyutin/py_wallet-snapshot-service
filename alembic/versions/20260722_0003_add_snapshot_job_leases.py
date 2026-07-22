"""add snapshot worker leases

Revision ID: 20260722_0003
Revises: 20260710_0002
Create Date: 2026-07-22
"""

import sqlalchemy as sa

from alembic import op

revision = "20260722_0003"
down_revision = "20260710_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("snapshot_runs", sa.Column("worker_id", sa.String(length=64), nullable=True))
    op.add_column(
        "snapshot_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_snapshot_runs_status_lease",
        "snapshot_runs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_runs_status_lease", table_name="snapshot_runs")
    op.drop_column("snapshot_runs", "lease_expires_at")
    op.drop_column("snapshot_runs", "worker_id")
