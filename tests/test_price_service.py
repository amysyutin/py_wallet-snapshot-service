from decimal import Decimal

import pytest

from app.config import Settings
from app.services.price_service import PriceService


def _settings(environment: str) -> Settings:
    token = (
        "a-strong-production-internal-token-value"
        if environment in {"staging", "production"}
        else "local-test-token"
    )
    return Settings(
        _env_file=None,
        environment=environment,
        internal_api_token=token,
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_secure_environments_do_not_use_static_dev_prices(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
):
    service = PriceService(_settings(environment))
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)
    monkeypatch.setattr(service, "_fetch_fiat_usd_rate", lambda _symbol: None)

    assert service.get_usd_price("ETH") == (None, None)


@pytest.mark.parametrize("environment", ["local", "development", "test"])
def test_non_secure_environments_keep_explicit_static_dev_prices(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
):
    service = PriceService(_settings(environment))
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)
    monkeypatch.setattr(service, "_fetch_fiat_usd_rate", lambda _symbol: None)

    assert service.get_usd_price("ETH") == (Decimal("3000"), "static_dev")


def test_sol_price_uses_coingecko_mapping(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []

    def fetch(symbol: str):
        observed.append(symbol)
        return Decimal("175.25")

    monkeypatch.setattr(service, "_fetch_coingecko_price", fetch)

    assert service.get_usd_price("sol") == (Decimal("175.25"), "coingecko")
    assert observed == ["SOL"]


def test_fiat_ticker_uses_frankfurter_rate(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)

    def fetch(symbol: str):
        observed.append(symbol)
        return Decimal("1.1641")

    monkeypatch.setattr(service, "_fetch_fiat_usd_rate", fetch)

    assert service.get_usd_price("eur") == (Decimal("1.1641"), "frankfurter")
    assert service.get_usd_price("EUR") == (Decimal("1.1641"), "frankfurter")
    assert observed == ["EUR"]


def test_usd_fiat_rate_does_not_call_provider(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)

    assert service.get_usd_price("USD") == (Decimal("1"), "frankfurter")


def test_frankfurter_rate_response_is_parsed(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []

    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"rate": 1.1641}

    class Client:
        def __init__(self, *, timeout: int):
            assert timeout == 3

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def get(url: str):
            observed.append(url)
            return Response()

    monkeypatch.setattr("app.services.price_service.httpx.Client", Client)

    assert service._fetch_fiat_usd_rate("EUR") == Decimal("1.1641")
    assert observed == ["https://api.frankfurter.dev/v2/rate/EUR/USD"]


def test_unknown_ticker_remains_unpriced_in_production(
    monkeypatch: pytest.MonkeyPatch,
):
    service = PriceService(_settings("production"))
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)
    monkeypatch.setattr(service, "_fetch_fiat_usd_rate", lambda _symbol: None)

    assert service.get_usd_price("UNKNOWN") == (None, None)


def test_token_price_uses_contract_lookup_and_cache(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []

    def fetch(platform: str, contract_address: str):
        observed.append((platform, contract_address))
        return Decimal("78619")

    monkeypatch.setattr(service, "_fetch_coingecko_token_price", fetch)
    address = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"

    assert service.get_token_usd_price("Ethereum", address) == (
        Decimal("78619"),
        "coingecko",
    )
    assert service.get_token_usd_price("ethereum", address.lower()) == (
        Decimal("78619"),
        "coingecko",
    )
    assert observed == [("ethereum", address.lower())]


def test_token_price_cache_isolated_by_platform(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []
    address = "0x0000000000000000000000000000000000000001"

    def fetch(platform: str, contract_address: str):
        observed.append((platform, contract_address))
        return Decimal("2")

    monkeypatch.setattr(service, "_fetch_coingecko_token_price", fetch)

    assert service.get_token_usd_price("ethereum", address) == (
        Decimal("2"),
        "coingecko",
    )
    assert service.get_token_usd_price("base", address) == (
        Decimal("2"),
        "coingecko",
    )
    assert observed == [("ethereum", address), ("base", address)]


def test_token_price_response_is_parsed(monkeypatch: pytest.MonkeyPatch):
    service = PriceService(_settings("production"))
    observed = []
    address = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"

    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {address: {"usd": 78619}}

    class Client:
        def __init__(self, *, timeout: int):
            assert timeout == 3

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def get(url: str, *, params: dict[str, str]):
            observed.append((url, params))
            return Response()

    monkeypatch.setattr("app.services.price_service.httpx.Client", Client)

    assert service._fetch_coingecko_token_price("ethereum", address) == Decimal("78619")
    assert observed == [
        (
            "https://api.coingecko.com/api/v3/simple/token_price/ethereum",
            {"contract_addresses": address, "vs_currencies": "usd"},
        )
    ]


@pytest.mark.parametrize(
    "address",
    ["", "0x123", "not-an-address", "0x" + "g" * 40],
)
def test_token_price_rejects_invalid_contract(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
):
    service = PriceService(_settings("production"))
    monkeypatch.setattr(
        service,
        "_fetch_coingecko_token_price",
        lambda *_args: pytest.fail("invalid contracts must not call CoinGecko"),
    )

    assert service.get_token_usd_price("ethereum", address) == (None, None)
