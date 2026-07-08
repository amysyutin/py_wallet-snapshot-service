from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_db
from app.main import create_app
from app.services.evm_collector import AssetBalance, ChainCollectionResult


def test_debug_evm_balance_success(client, monkeypatch):
    def fake_collect_chain(self, address: str, chain: str) -> ChainCollectionResult:
        return ChainCollectionResult(
            chain=chain,
            status="success",
            native_balance=Decimal("1.25"),
            total_usd=Decimal("3750"),
            rpc_latency_ms=120,
            balances=[
                AssetBalance(
                    symbol="ETH",
                    asset_address=None,
                    asset_type="native",
                    amount=Decimal("1.25"),
                    price_usd=Decimal("3000"),
                    value_usd=Decimal("3750"),
                    price_source="test",
                )
            ],
            error_type=None,
            error_message=None,
        )

    monkeypatch.setattr("app.api.debug.EvmCollector.collect_chain", fake_collect_chain)

    response = client.get(
        "/debug/evm-balance?chain=mainnet&address=0x74100A58eC575F7c9E127B464cAf4609e36ee0BB",
        headers={"X-Internal-Token": "test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"] == "mainnet"
    assert payload["address"] == "0x74100A58eC575F7c9E127B464cAf4609e36ee0BB"
    assert payload["status"] == "success"
    assert payload["rpc_latency_ms"] == 120
    assert payload["balances"][0]["symbol"] == "ETH"


def test_debug_evm_balance_requires_internal_token(client):
    response = client.get(
        "/debug/evm-balance?chain=mainnet&address=0x74100A58eC575F7c9E127B464cAf4609e36ee0BB"
    )
    assert response.status_code == 401


def test_debug_evm_balance_returns_failed_for_invalid_address(client):
    response = client.get(
        "/debug/evm-balance?chain=mainnet&address=not-an-address",
        headers={"X-Internal-Token": "test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_type"] == "invalid_address"
    assert payload["error_message"] == "invalid EVM address"


def test_debug_evm_balance_hidden_when_debug_disabled(monkeypatch, db_session):
    monkeypatch.setenv("DEBUG_ENDPOINTS_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as test_client:
        response = test_client.get(
            "/debug/evm-balance?chain=mainnet&address=0x74100A58eC575F7c9E127B464cAf4609e36ee0BB",
            headers={"X-Internal-Token": "test-token"},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 404
