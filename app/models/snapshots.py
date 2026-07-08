from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import JobStatus


class SnapshotRun(Base):
    __tablename__ = "snapshot_runs"
    __table_args__ = (
        Index("ix_snapshot_runs_user_status_created", "user_id", "status", "created_at"),
        Index("ix_snapshot_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    group_id: Mapped[int | None] = mapped_column(index=True)
    wallet_id: Mapped[int | None] = mapped_column(index=True)
    parent_run_id: Mapped[int | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default=JobStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    wallet_snapshots: Mapped[list["WalletSnapshot"]] = relationship(
        back_populates="snapshot_run", cascade="all, delete-orphan"
    )


class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"
    __table_args__ = (
        Index("ix_wallet_snapshots_run_wallet", "snapshot_run_id", "wallet_id"),
        Index("ix_wallet_snapshots_run_group", "snapshot_run_id", "group_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_run_id: Mapped[int] = mapped_column(ForeignKey("snapshot_runs.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(index=True)
    group_id: Mapped[int | None] = mapped_column(index=True)
    wallet_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    total_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    snapshot_run: Mapped[SnapshotRun] = relationship(back_populates="wallet_snapshots")
    chain_snapshots: Mapped[list["ChainSnapshot"]] = relationship(
        back_populates="wallet_snapshot", cascade="all, delete-orphan"
    )


class ChainSnapshot(Base):
    __tablename__ = "chain_snapshots"
    __table_args__ = (Index("ix_chain_snapshots_wallet_chain", "wallet_snapshot_id", "chain"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_snapshot_id: Mapped[int] = mapped_column(ForeignKey("wallet_snapshots.id"), index=True)
    chain: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    native_balance: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    total_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    rpc_latency_ms: Mapped[int | None]
    error_type: Mapped[str | None] = mapped_column(String(64), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wallet_snapshot: Mapped[WalletSnapshot] = relationship(back_populates="chain_snapshots")
    balance_snapshots: Mapped[list["BalanceSnapshot"]] = relationship(
        back_populates="chain_snapshot", cascade="all, delete-orphan"
    )


class BalanceSnapshot(Base):
    __tablename__ = "snapshot_balance_snapshots"
    __table_args__ = (
        Index("ix_snapshot_balance_snapshots_chain_symbol", "chain_snapshot_id", "asset_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_snapshot_id: Mapped[int] = mapped_column(ForeignKey("chain_snapshots.id"), index=True)
    asset_symbol: Mapped[str] = mapped_column(String(32), index=True)
    asset_address: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    value_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    price_source: Mapped[str | None] = mapped_column(String(64))

    chain_snapshot: Mapped[ChainSnapshot] = relationship(back_populates="balance_snapshots")
