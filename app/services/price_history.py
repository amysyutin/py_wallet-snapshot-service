import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.external import Asset, PriceHistory
from app.services.evm_collector import AssetBalance

logger = logging.getLogger(__name__)

PROVIDER_PRICE_SOURCES = frozenset({"coingecko", "frankfurter"})


class PriceHistoryRecorder:
    """Persist one provider-backed observation per asset and snapshot job."""

    def __init__(self, db: Session):
        self.db = db
        self._recorded_assets: set[tuple[str, str, str]] = set()

    def begin_job(self) -> None:
        self._recorded_assets.clear()

    def record(
        self,
        *,
        chain: str,
        balance: AssetBalance,
        observed_at: datetime,
    ) -> bool:
        source = balance.price_source
        price = balance.price_usd
        if (
            source not in PROVIDER_PRICE_SOURCES
            or price is None
            or price <= 0
            or balance.amount <= 0
        ):
            return False

        normalized_chain = chain.strip().lower()
        normalized_symbol = balance.symbol.strip().upper()
        normalized_address = self._normalize_address(balance.asset_address)
        identity = (
            normalized_chain,
            normalized_address or "",
            normalized_symbol if normalized_address is None else "",
        )
        if identity in self._recorded_assets:
            return False

        try:
            with self.db.begin_nested():
                asset = self._find_or_create_asset(
                    chain=normalized_chain,
                    symbol=normalized_symbol,
                    contract_address=normalized_address,
                    decimals=balance.decimals,
                )
                self.db.add(
                    PriceHistory(
                        asset_id=asset.id,
                        price_at=observed_at,
                        price_usd=price,
                        source=source,
                    )
                )
                self.db.flush()
        except SQLAlchemyError:
            logger.warning(
                "price_history_record_failed",
                extra={
                    "chain": normalized_chain,
                    "symbol": normalized_symbol,
                    "source": source,
                },
                exc_info=True,
            )
            return False

        self._recorded_assets.add(identity)
        return True

    def _find_or_create_asset(
        self,
        *,
        chain: str,
        symbol: str,
        contract_address: str | None,
        decimals: int,
    ) -> Asset:
        query = select(Asset).where(Asset.chain == chain)
        if contract_address is None:
            query = query.where(
                Asset.contract_address.is_(None),
                func.upper(Asset.symbol) == symbol,
            )
        elif contract_address.startswith("0x"):
            query = query.where(func.lower(Asset.contract_address) == contract_address)
        else:
            query = query.where(Asset.contract_address == contract_address)

        asset = self.db.scalar(query.limit(1))
        if asset is not None:
            return asset

        asset = Asset(
            symbol=symbol,
            name=symbol,
            contract_address=contract_address,
            chain=chain,
            decimals=decimals,
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    @staticmethod
    def _normalize_address(address: str | None) -> str | None:
        if address is None:
            return None
        normalized = address.strip()
        lowered = normalized.lower()
        return lowered if lowered.startswith("0x") else normalized
