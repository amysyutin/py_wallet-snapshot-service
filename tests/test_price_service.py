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
