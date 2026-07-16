import json
from decimal import Decimal
from unittest.mock import patch

import httpx

from app.enums import ErrorType
from app.services.chain_config import ChainConfig, TokenConfig
from app.services.evm_collector import EvmCollector

REAL_HTTPX_CLIENT = httpx.Client


class StaticPriceService:
    def get_usd_price(self, symbol: str):
        prices = {"ETH": Decimal("3000"), "USDC": Decimal("1")}
        return prices[symbol], "test"


def _config(*rpc_urls: str, expected_chain_id: int = 8453) -> ChainConfig:
    return ChainConfig(
        name="base",
        native_symbol="ETH",
        expected_chain_id=expected_chain_id,
        rpc_urls=rpc_urls,
        timeout_seconds=2,
        tokens=(
            TokenConfig(
                "USDC",
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            ),
        ),
    )


def _client_factory(transport: httpx.MockTransport):
    return lambda *args, **kwargs: REAL_HTTPX_CLIENT(transport=transport, timeout=2)


def test_collects_native_and_erc20_balances():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        if method == "eth_chainId":
            result = hex(8453)
        elif method == "eth_getBalance":
            result = hex(10**18)
        elif payload["params"][0]["data"] == "0x313ce567":
            result = hex(6)
        else:
            result = hex(2_500_000)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    transport = httpx.MockTransport(handler)
    collector = EvmCollector({"base": _config("https://base.test")}, StaticPriceService())
    with patch(
        "app.services.evm_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        result = collector.collect_chain(
            "0x0000000000000000000000000000000000000001",
            "base",
        )

    assert result.status == "success"
    assert result.total_usd == Decimal("3002.5")
    assert [balance.symbol for balance in result.balances] == ["ETH", "USDC"]
    assert result.balances[1].amount == Decimal("2.5")
    assert result.balances[1].asset_type == "erc20"


def test_fails_over_and_temporarily_skips_rate_limited_rpc():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "primary.test":
            return httpx.Response(429, json={"error": "rate limited"})

        payload = json.loads(request.content)
        if payload["method"] == "eth_chainId":
            result = hex(8453)
        elif payload["method"] == "eth_getBalance":
            result = "0x0"
        elif payload["params"][0]["data"] == "0x313ce567":
            result = hex(6)
        else:
            result = "0x0"
        return httpx.Response(200, json={"result": result})

    transport = httpx.MockTransport(handler)
    collector = EvmCollector(
        {"base": _config("https://primary.test", "https://backup.test")},
        StaticPriceService(),
        cooldown_seconds=60,
    )
    with patch(
        "app.services.evm_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        first = collector.collect_chain(
            "0x0000000000000000000000000000000000000001",
            "base",
        )
        second = collector.collect_chain(
            "0x0000000000000000000000000000000000000001",
            "base",
        )

    assert first.status == "success"
    assert second.status == "success"
    assert calls.count("primary.test") == 1
    assert calls.count("backup.test") == 8


def test_rejects_rpc_for_wrong_chain():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": hex(1)})

    transport = httpx.MockTransport(handler)
    collector = EvmCollector({"base": _config("https://wrong.test")}, StaticPriceService())
    with patch(
        "app.services.evm_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        result = collector.collect_chain(
            "0x0000000000000000000000000000000000000001",
            "base",
        )

    assert result.status == "failed"
    assert result.error_type == ErrorType.BAD_CONFIG.value
