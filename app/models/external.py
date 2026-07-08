from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)


class WalletGroup(Base):
    __tablename__ = "wallet_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(255))


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    group_id: Mapped[int | None] = mapped_column(index=True)
    label: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    chain_type: Mapped[str | None] = mapped_column(String(50))
    wallet_type: Mapped[str] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    contract_address: Mapped[str | None] = mapped_column(String(128))
    chain: Mapped[str] = mapped_column(String(32))
    decimals: Mapped[int] = mapped_column(default=18)


class ManualBalance(Base):
    __tablename__ = "manual_balances"

    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
