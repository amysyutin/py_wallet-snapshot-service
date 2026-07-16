import time
from decimal import Decimal

import httpx

from app.config import Settings, get_settings


class PriceService:
    symbol_to_coingecko = {
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "BTC": "bitcoin",
        "USDT": "tether",
        "USDC": "usd-coin",
        "USDC.E": "usd-coin",
        "USDBC": "usd-coin",
        "BINANCE_PEG_USDC": "usd-coin",
    }
    dev_prices = {
        "ETH": Decimal("3000"),
        "BNB": Decimal("600"),
        "BTC": Decimal("65000"),
        "USDT": Decimal("1"),
        "USDC": Decimal("1"),
        "USDC.E": Decimal("1"),
        "USDBC": Decimal("1"),
        "BINANCE_PEG_USDC": Decimal("1"),
    }

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cache: dict[str, tuple[float, Decimal, str]] = {}

    def get_usd_price(self, symbol: str) -> tuple[Decimal | None, str | None]:
        normalized = symbol.upper()
        cached = self._cache.get(normalized)
        now = time.time()
        if cached and now - cached[0] < self.settings.price_cache_ttl_seconds:
            return cached[1], cached[2]

        price = self._fetch_coingecko_price(normalized)
        if price is not None:
            self._cache[normalized] = (now, price, "coingecko")
            return price, "coingecko"

        fallback = self.dev_prices.get(normalized)
        if fallback is not None:
            self._cache[normalized] = (now, fallback, "static_dev")
            return fallback, "static_dev"
        return None, None

    def _fetch_coingecko_price(self, symbol: str) -> Decimal | None:
        coin_id = self.symbol_to_coingecko.get(symbol)
        if not coin_id:
            return None
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(
                    f"{self.settings.coingecko_base_url}/simple/price",
                    params={"ids": coin_id, "vs_currencies": "usd"},
                )
                response.raise_for_status()
                value = response.json().get(coin_id, {}).get("usd")
                return Decimal(str(value)) if value is not None else None
        except Exception:
            return None
