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
            return httpx.Response(
                429,
                headers={"Retry-After": "120"},
                json={"error": "rate limited"},
            )

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
    with (
        patch(
            "app.services.evm_collector.httpx.Client",
            side_effect=_client_factory(transport),
        ),
        patch("app.services.evm_collector.monotonic", return_value=100),
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
    assert calls.count("backup.test") == 6
    assert collector._unavailable_until["https://primary.test"] == 220


def test_reports_circuit_open_without_rehitting_rate_limited_rpc():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "45"})

    transport = httpx.MockTransport(handler)
    collector = EvmCollector(
        {"base": _config("https://limited.test")},
        StaticPriceService(),
    )
    with (
        patch(
            "app.services.evm_collector.httpx.Client",
            side_effect=_client_factory(transport),
        ),
        patch("app.services.evm_collector.monotonic", return_value=100),
    ):
        first = collector.collect_chain(
            "0x0000000000000000000000000000000000000001",
            "base",
        )
        second = collector.collect_chain(
            "0x0000000000000000000000000000000000000002",
            "base",
        )

    assert first.error_type == ErrorType.RATE_LIMIT.value
    assert second.error_type == ErrorType.CIRCUIT_OPEN.value
    assert "retry in 45s" in (second.error_message or "")
    assert calls == 1


def test_caches_chain_id_and_token_decimals_between_wallets():
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        methods.append(method)
        if method == "eth_chainId":
            result = hex(8453)
        elif method == "eth_getBalance":
            result = "0x0"
        elif payload["params"][0]["data"] == "0x313ce567":
            result = hex(6)
        else:
            result = "0x0"
        return httpx.Response(200, json={"result": result})

    transport = httpx.MockTransport(handler)
    collector = EvmCollector(
        {"base": _config("https://base.test")},
        StaticPriceService(),
    )
    with patch(
        "app.services.evm_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        for suffix in ("1", "2"):
            result = collector.collect_chain(
                f"0x{'0' * 39}{suffix}",
                "base",
            )
            assert result.status == "success"

    assert methods.count("eth_chainId") == 1
    assert methods.count("eth_getBalance") == 2
    assert methods.count("eth_call") == 3


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
