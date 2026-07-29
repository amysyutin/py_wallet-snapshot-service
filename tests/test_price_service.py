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

    assert service.get_usd_price("ETH") == (None, None)


@pytest.mark.parametrize("environment", ["local", "development", "test"])
def test_non_secure_environments_keep_explicit_static_dev_prices(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
):
    service = PriceService(_settings(environment))
    monkeypatch.setattr(service, "_fetch_coingecko_price", lambda _symbol: None)

    assert service.get_usd_price("ETH") == (Decimal("3000"), "static_dev")
