import json
from decimal import Decimal
from unittest.mock import patch

import httpx

from app.enums import ErrorType
from app.services.solana_collector import (
    SPL_TOKEN_PROGRAM_ID,
    TRACKED_SPL_TOKENS,
    SolanaCollector,
)

REAL_HTTPX_CLIENT = httpx.Client
OWNER = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_MINT = TRACKED_SPL_TOKENS[0].mint
USDT_MINT = TRACKED_SPL_TOKENS[1].mint


class StaticPriceService:
    def get_usd_price(self, symbol: str):
        prices = {"SOL": Decimal("100"), "USDC": Decimal("1"), "USDT": Decimal("1")}
        return prices[symbol], "test"


def _client_factory(transport: httpx.MockTransport):
    return lambda *args, **kwargs: REAL_HTTPX_CLIENT(transport=transport, timeout=2)


def _token_account(mint: str, amount: str, decimals: int = 6) -> dict[str, object]:
    return {
        "account": {
            "data": {
                "parsed": {
                    "info": {
                        "mint": mint,
                        "tokenAmount": {"amount": amount, "decimals": decimals},
                    }
                }
            }
        }
    }


def _success_response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    if payload["method"] == "getBalance":
        result = {"context": {"slot": 1}, "value": 2_000_000_000}
    else:
        assert payload["params"][1] == {"programId": SPL_TOKEN_PROGRAM_ID}
        assert payload["params"][2]["encoding"] == "jsonParsed"
        result = {
            "context": {"slot": 1},
            "value": [
                _token_account(USDC_MINT, "1500000"),
                _token_account(USDC_MINT, "1000000"),
                _token_account(USDT_MINT, "3000000"),
                _token_account("So11111111111111111111111111111111111111112", "999"),
            ],
        }
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


def test_collects_sol_and_aggregates_tracked_spl_token_accounts():
    transport = httpx.MockTransport(_success_response)
    collector = SolanaCollector(("https://solana.test",), StaticPriceService())

    with patch(
        "app.services.solana_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        result = collector.collect_wallet(OWNER)

    assert result.status == "success"
    assert result.native_balance == Decimal("2")
    assert result.total_usd == Decimal("205.5")
    assert [balance.symbol for balance in result.balances] == ["SOL", "USDC", "USDT"]
    assert [balance.amount for balance in result.balances] == [
        Decimal("2"),
        Decimal("2.5"),
        Decimal("3"),
    ]
    assert [balance.asset_type for balance in result.balances] == ["native", "spl", "spl"]


def test_rejects_invalid_address_without_calling_rpc():
    collector = SolanaCollector(("https://solana.test",), StaticPriceService())

    result = collector.collect_wallet("not-a-solana-address")

    assert result.status == "failed"
    assert result.error_type == ErrorType.INVALID_ADDRESS.value
    assert collector._client is None


def test_reports_missing_rpc_url_for_valid_address():
    result = SolanaCollector((), StaticPriceService()).collect_wallet(OWNER)

    assert result.status == "failed"
    assert result.error_type == ErrorType.MISSING_RPC_URL.value


def test_fails_over_and_temporarily_skips_rate_limited_rpc():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "primary.test":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return _success_response(request)

    transport = httpx.MockTransport(handler)
    collector = SolanaCollector(
        ("https://primary.test", "https://backup.test"),
        StaticPriceService(),
    )
    with (
        patch(
            "app.services.solana_collector.httpx.Client",
            side_effect=_client_factory(transport),
        ),
        patch("app.services.solana_collector.monotonic", return_value=100),
    ):
        first = collector.collect_wallet(OWNER)
        second = collector.collect_wallet(OWNER)

    assert first.status == "success"
    assert second.status == "success"
    assert calls.count("primary.test") == 1
    assert calls.count("backup.test") == 4
    assert collector._unavailable_until["https://primary.test"] == 220


def test_bounds_json_rpc_errors_without_exposing_provider_response():
    secret_detail = "provider-secret-diagnostic"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"message": secret_detail}},
        )

    transport = httpx.MockTransport(handler)
    collector = SolanaCollector(("https://solana.test",), StaticPriceService())
    with patch(
        "app.services.solana_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        result = collector.collect_wallet(OWNER)

    assert result.status == "failed"
    assert result.error_type == ErrorType.RPC_ERROR.value
    assert secret_detail not in (result.error_message or "")


def test_rejects_malformed_tracked_token_amount():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        result = (
            {"value": 0}
            if payload["method"] == "getBalance"
            else {"value": [_token_account(USDC_MINT, "not-an-integer")]}
        )
        return httpx.Response(200, json={"result": result})

    transport = httpx.MockTransport(handler)
    collector = SolanaCollector(("https://solana.test",), StaticPriceService())
    with patch(
        "app.services.solana_collector.httpx.Client",
        side_effect=_client_factory(transport),
    ):
        result = collector.collect_wallet(OWNER)

    assert result.status == "failed"
    assert result.error_type == ErrorType.RPC_ERROR.value
    assert result.balances == []
