from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssetType, ChainStatus, ErrorType
from app.models.external import Asset, ManualBalance
from app.services.evm_collector import AssetBalance, ChainCollectionResult
from app.services.price_service import PriceService


class ManualCollector:
    def __init__(self, db: Session, price_service: PriceService):
        self.db = db
        self.price_service = price_service

    def collect_wallet(self, wallet_id: int) -> ChainCollectionResult:
        rows = list(
            self.db.execute(
                select(ManualBalance, Asset.symbol)
                .join(Asset, Asset.id == ManualBalance.asset_id)
                .where(ManualBalance.wallet_id == wallet_id)
                .order_by(Asset.symbol)
            )
        )
        balances: list[AssetBalance] = []
        total = Decimal("0")
        missing_prices: list[str] = []

        for row, symbol in rows:
            price = row.price_usd
            source = "manual"
            if price is None:
                price, source = self.price_service.get_usd_price(symbol)
            if price is None:
                value = Decimal("0")
                source = None
                missing_prices.append(symbol)
            else:
                value = row.amount * price
            total += value
            balances.append(
                AssetBalance(
                    symbol=symbol.upper(),
                    asset_address=None,
                    asset_type=AssetType.MANUAL.value,
                    amount=row.amount,
                    price_usd=price,
                    value_usd=value,
                    price_source=source,
                )
            )

        return ChainCollectionResult(
            chain="manual",
            status=ChainStatus.SUCCESS.value if not missing_prices else ChainStatus.FAILED.value,
            native_balance=None,
            total_usd=total,
            rpc_latency_ms=None,
            balances=balances,
            error_type=ErrorType.PRICE_UNAVAILABLE.value if missing_prices else None,
            error_message=f"missing prices for: {', '.join(missing_prices)}"
            if missing_prices
            else None,
        )
