"""add first-wallet activation channel

Revision ID: 20260727_0004
Revises: 20260722_0003
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0004"
down_revision = "20260722_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE snapshot_runs ADD COLUMN IF NOT EXISTS activation_channel VARCHAR(16)")


def downgrade() -> None:
    op.execute("ALTER TABLE snapshot_runs DROP COLUMN IF EXISTS activation_channel")
