import time
from decimal import Decimal

import httpx

from app.config import SECURE_ENVIRONMENTS, Settings, get_settings


class PriceService:
    symbol_to_coingecko = {
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "BTC": "bitcoin",
        "SOL": "solana",
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
        "SOL": Decimal("150"),
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

        price = self._fetch_fiat_usd_rate(normalized)
        if price is not None:
            self._cache[normalized] = (now, price, "frankfurter")
            return price, "frankfurter"

        fallback = (
            None
            if self.settings.environment in SECURE_ENVIRONMENTS
            else self.dev_prices.get(normalized)
        )
        if fallback is not None:
            self._cache[normalized] = (now, fallback, "static_dev")
            return fallback, "static_dev"
        return None, None

    def get_token_usd_price(
        self,
        platform: str,
        contract_address: str,
    ) -> tuple[Decimal | None, str | None]:
        normalized_platform = platform.strip().lower()
        normalized_address = contract_address.strip().lower()
        if not normalized_platform or not self._is_evm_contract(normalized_address):
            return None, None

        cache_key = f"token:{normalized_platform}:{normalized_address}"
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and now - cached[0] < self.settings.price_cache_ttl_seconds:
            return cached[1], cached[2]

        price = self._fetch_coingecko_token_price(
            normalized_platform,
            normalized_address,
        )
        if price is None:
            return None, None
        self._cache[cache_key] = (now, price, "coingecko")
        return price, "coingecko"

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

    def _fetch_coingecko_token_price(
        self,
        platform: str,
        contract_address: str,
    ) -> Decimal | None:
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(
                    f"{self.settings.coingecko_base_url}/simple/token_price/{platform}",
                    params={
                        "contract_addresses": contract_address,
                        "vs_currencies": "usd",
                    },
                )
                response.raise_for_status()
                token_data = response.json().get(contract_address, {})
                value = token_data.get("usd") if isinstance(token_data, dict) else None
                price = Decimal(str(value)) if value is not None else None
                return price if price is not None and price > 0 else None
        except Exception:
            return None

    @staticmethod
    def _is_evm_contract(contract_address: str) -> bool:
        if len(contract_address) != 42 or not contract_address.startswith("0x"):
            return False
        try:
            int(contract_address[2:], 16)
        except ValueError:
            return False
        return True

    def _fetch_fiat_usd_rate(self, symbol: str) -> Decimal | None:
        """Resolve an ISO 4217 ticker to the value of one unit in USD."""
        if len(symbol) != 3 or not symbol.isalpha():
            return None
        if symbol == "USD":
            return Decimal("1")
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{self.settings.frankfurter_base_url}/rate/{symbol}/USD")
                response.raise_for_status()
                value = response.json().get("rate")
                price = Decimal(str(value)) if value is not None else None
                return price if price is not None and price > 0 else None
        except Exception:
            return None
