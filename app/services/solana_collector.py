from dataclasses import dataclass
from decimal import Decimal
from time import monotonic, perf_counter
from typing import Any

import httpx

from app.enums import AssetType, ChainStatus, ErrorType
from app.metrics import rpc_attempts_total, rpc_circuit_open_total, rpc_failovers_total
from app.services.evm_collector import AssetBalance, ChainCollectionResult, RpcAttemptError
from app.services.price_service import PriceService

SOLANA_CHAIN = "solana"
LAMPORTS_PER_SOL = Decimal("1000000000")
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_VALUES = {character: index for index, character in enumerate(BASE58_ALPHABET)}


@dataclass(frozen=True)
class SplTokenConfig:
    symbol: str
    mint: str
    decimals: int


TRACKED_SPL_TOKENS = (
    SplTokenConfig(
        symbol="USDC",
        mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        decimals=6,
    ),
    SplTokenConfig(
        symbol="USDT",
        mint="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        decimals=6,
    ),
)


class SolanaCollector:
    def __init__(
        self,
        rpc_urls: tuple[str, ...],
        price_service: PriceService,
        timeout_seconds: int = 8,
        cooldown_seconds: int = 60,
        tokens: tuple[SplTokenConfig, ...] = TRACKED_SPL_TOKENS,
    ):
        self.rpc_urls = rpc_urls
        self.price_service = price_service
        self.timeout_seconds = timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self.tokens = tokens
        self._unavailable_until: dict[str, float] = {}
        self._client: httpx.Client | None = None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    def collect_wallet(self, address: str) -> ChainCollectionResult:
        if not self._is_valid_address(address):
            return self._failed(ErrorType.INVALID_ADDRESS.value, "invalid Solana address")
        if not self.rpc_urls:
            return self._failed(
                ErrorType.MISSING_RPC_URL.value,
                "Solana RPC URL is not configured",
            )

        available = [
            (index, url)
            for index, url in enumerate(self.rpc_urls)
            if self._unavailable_until.get(url, 0) <= monotonic()
        ]
        if not available:
            retry_in = max(
                1,
                int(min(self._unavailable_until[url] for url in self.rpc_urls) - monotonic()),
            )
            return self._failed(
                ErrorType.CIRCUIT_OPEN.value,
                f"all Solana RPC endpoints are cooling down; retry in {retry_in}s",
            )

        last_error: RpcAttemptError | None = None
        for position, (provider_index, rpc_url) in enumerate(available):
            started = perf_counter()
            try:
                result = self._collect_from_endpoint(address, rpc_url)
            except RpcAttemptError as exc:
                last_error = exc
                cooldown = min(
                    3600,
                    max(1, exc.retry_after_seconds or self.cooldown_seconds),
                )
                self._unavailable_until[rpc_url] = monotonic() + cooldown
                rpc_attempts_total.labels(
                    SOLANA_CHAIN,
                    str(provider_index),
                    "failed",
                    exc.error_type,
                ).inc()
                rpc_circuit_open_total.labels(SOLANA_CHAIN, str(provider_index)).inc()
                if position < len(available) - 1:
                    rpc_failovers_total.labels(SOLANA_CHAIN).inc()
                continue

            result.rpc_latency_ms = int((perf_counter() - started) * 1000)
            self._unavailable_until.pop(rpc_url, None)
            rpc_attempts_total.labels(
                SOLANA_CHAIN,
                str(provider_index),
                "success",
                "none",
            ).inc()
            return result

        assert last_error is not None
        return self._failed(last_error.error_type, str(last_error)[:250])

    def _collect_from_endpoint(self, address: str, rpc_url: str) -> ChainCollectionResult:
        client = self._get_client()
        balance_result = self._rpc_call(
            client,
            rpc_url,
            "getBalance",
            [address, {"commitment": "finalized"}],
        )
        lamports = self._result_value_int(balance_result, "getBalance")
        native_amount = Decimal(lamports) / LAMPORTS_PER_SOL

        token_result = self._rpc_call(
            client,
            rpc_url,
            "getTokenAccountsByOwner",
            [
                address,
                {"programId": SPL_TOKEN_PROGRAM_ID},
                {"encoding": "jsonParsed", "commitment": "finalized"},
            ],
        )
        raw_token_amounts = self._parse_token_accounts(token_result)

        native_price, native_source = self.price_service.get_usd_price("SOL")
        native_value = native_amount * native_price if native_price is not None else Decimal("0")
        balances = [
            AssetBalance(
                symbol="SOL",
                asset_address=None,
                asset_type=AssetType.NATIVE.value,
                amount=native_amount,
                price_usd=native_price,
                value_usd=native_value,
                price_source=native_source,
                decimals=9,
            )
        ]
        for token in self.tokens:
            amount = Decimal(raw_token_amounts[token.mint]) / (Decimal(10) ** token.decimals)
            price, source = self.price_service.get_usd_price(token.symbol)
            value = amount * price if price is not None else Decimal("0")
            balances.append(
                AssetBalance(
                    symbol=token.symbol,
                    asset_address=token.mint,
                    asset_type=AssetType.SPL.value,
                    amount=amount,
                    price_usd=price,
                    value_usd=value,
                    price_source=source,
                    decimals=token.decimals,
                )
            )

        return ChainCollectionResult(
            chain=SOLANA_CHAIN,
            status=ChainStatus.SUCCESS.value,
            native_balance=native_amount,
            total_usd=sum((balance.value_usd for balance in balances), Decimal("0")),
            rpc_latency_ms=None,
            balances=balances,
        )

    def _parse_token_accounts(self, result: object) -> dict[str, int]:
        if not isinstance(result, dict) or not isinstance(result.get("value"), list):
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                "RPC response for getTokenAccountsByOwner has no account list",
            )

        token_by_mint = {token.mint: token for token in self.tokens}
        amounts = {token.mint: 0 for token in self.tokens}
        for account in result["value"]:
            try:
                info = account["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                token_amount = info["tokenAmount"]
            except (KeyError, TypeError):
                raise RpcAttemptError(
                    ErrorType.RPC_ERROR.value,
                    "Solana RPC returned a malformed token account",
                ) from None

            token = token_by_mint.get(mint)
            if token is None:
                continue
            raw_amount = token_amount.get("amount") if isinstance(token_amount, dict) else None
            decimals = token_amount.get("decimals") if isinstance(token_amount, dict) else None
            if (
                not isinstance(raw_amount, str)
                or not raw_amount.isdigit()
                or not isinstance(decimals, int)
                or isinstance(decimals, bool)
                or decimals != token.decimals
            ):
                raise RpcAttemptError(
                    ErrorType.RPC_ERROR.value,
                    f"Solana RPC returned an invalid {token.symbol} token amount",
                )
            amounts[mint] += int(raw_amount)
        return amounts

    @staticmethod
    def _result_value_int(result: object, method: str) -> int:
        value = result.get("value") if isinstance(result, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"RPC response for {method} has no non-negative integer value",
            )
        return value

    @staticmethod
    def _rpc_call(
        client: httpx.Client,
        rpc_url: str,
        method: str,
        params: list[object],
    ) -> Any:
        try:
            response = client.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            )
            if response.status_code == 429:
                raise RpcAttemptError(
                    ErrorType.RATE_LIMIT.value,
                    "Solana RPC rate limit exceeded",
                    retry_after_seconds=SolanaCollector._retry_after_seconds(response),
                )
            response.raise_for_status()
            payload = response.json()
        except RpcAttemptError:
            raise
        except httpx.TimeoutException as exc:
            raise RpcAttemptError(
                ErrorType.TIMEOUT.value,
                "Solana RPC request timed out",
            ) from exc
        except httpx.ConnectError as exc:
            raise RpcAttemptError(
                ErrorType.CONNECTION_ERROR.value,
                "Solana RPC connection failed",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"Solana RPC returned HTTP {exc.response.status_code}",
            ) from exc
        except Exception as exc:
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                "Solana RPC returned an invalid response",
            ) from exc

        if not isinstance(payload, dict):
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"RPC response for {method} is not an object",
            )
        if payload.get("error") is not None:
            error_text = str(payload["error"])
            error_type = (
                ErrorType.RATE_LIMIT.value
                if "rate" in error_text.lower() or "too many" in error_text.lower()
                else ErrorType.RPC_ERROR.value
            )
            message = (
                "Solana RPC rate limit exceeded"
                if error_type == ErrorType.RATE_LIMIT.value
                else f"Solana RPC error during {method}"
            )
            raise RpcAttemptError(error_type, message)
        if "result" not in payload:
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"RPC response for {method} has no result",
            )
        return payload["result"]

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> int | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(1, int(value))
        except ValueError:
            return None

    @staticmethod
    def _is_valid_address(address: str | None) -> bool:
        if not address or address != address.strip():
            return False
        try:
            number = 0
            for character in address:
                number = number * 58 + BASE58_VALUES[character]
        except KeyError:
            return False

        decoded = (
            number.to_bytes((number.bit_length() + 7) // 8, byteorder="big") if number else b""
        )
        leading_zeroes = len(address) - len(address.lstrip("1"))
        return len(b"\0" * leading_zeroes + decoded) == 32

    @staticmethod
    def _failed(error_type: str, error_message: str) -> ChainCollectionResult:
        return ChainCollectionResult(
            chain=SOLANA_CHAIN,
            status=ChainStatus.FAILED.value,
            native_balance=None,
            total_usd=Decimal("0"),
            rpc_latency_ms=None,
            balances=[],
            error_type=error_type,
            error_message=error_message,
        )
