import os
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SNAPSHOT_WORKER_ENABLED", "false")
os.environ.setdefault("SNAPSHOT_SCHEDULER_ENABLED", "false")
os.environ.setdefault("SNAPSHOT_ENABLED_CHAINS", "mainnet,base,arbitrum,bnb,linea")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-token")

from app.config import get_settings
from app.db import Base, get_db
from app.main import create_app
from app.models.external import Asset, ManualBalance, User, Wallet


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture()
def client(monkeypatch, db_session: Session) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SNAPSHOT_WORKER_ENABLED", "false")
    monkeypatch.setenv("SNAPSHOT_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("SNAPSHOT_ENABLED_CHAINS", "mainnet,base,arbitrum,bnb,linea")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token")
    monkeypatch.setenv("DEBUG_ENDPOINTS_ENABLED", "true")
    get_settings.cache_clear()

    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_user_wallet(
    db: Session,
    *,
    wallet_type: str = "manual",
    address: str | None = None,
    user_id: int = 1,
    wallet_id: int = 1,
) -> Wallet:
    user = User(id=user_id, email=f"user{user_id}@example.test")
    wallet = Wallet(
        id=wallet_id,
        user_id=user_id,
        group_id=10,
        label="Wallet",
        address=address,
        chain_type="evm" if wallet_type == "evm" else None,
        wallet_type=wallet_type,
        is_active=True,
    )
    db.add_all([user, wallet])
    db.commit()
    return wallet


def seed_manual_balance(db: Session, wallet_id: int = 1, symbol: str = "USDC") -> None:
    asset = Asset(
        id=1,
        symbol=symbol,
        name=symbol,
        contract_address=None,
        chain="manual",
        decimals=18,
    )
    db.add(asset)
    db.add(
        ManualBalance(
            wallet_id=wallet_id,
            asset_id=asset.id,
            amount=Decimal("12.5"),
            price_usd=Decimal("1"),
        )
    )
    db.commit()
