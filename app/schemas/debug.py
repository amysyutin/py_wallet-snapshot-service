from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DebugJobItem(BaseModel):
    id: int
    user_id: int
    trigger_type: str
    scope_type: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class DebugJobsResponse(BaseModel):
    items: list[DebugJobItem]


class DebugBalanceItem(BaseModel):
    id: int
    asset_symbol: str
    amount: Decimal
    value_usd: Decimal
    price_source: str | None

    model_config = {"from_attributes": True}


class DebugChainItem(BaseModel):
    id: int
    chain: str
    status: str
    total_usd: Decimal
    rpc_latency_ms: int | None
    error_type: str | None
    error_message: str | None
    balances_count: int


class DebugWalletItem(BaseModel):
    id: int
    wallet_id: int
    group_id: int | None
    wallet_type: str
    status: str
    total_usd: Decimal
    error_message: str | None
    chains: list[DebugChainItem]


class DebugJobDetail(BaseModel):
    job: DebugJobItem
    wallets: list[DebugWalletItem]

