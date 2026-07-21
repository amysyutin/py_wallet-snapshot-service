from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from time import monotonic, perf_counter

import httpx

from app.enums import AssetType, ChainStatus, ErrorType
from app.metrics import rpc_attempts_total, rpc_circuit_open_total, rpc_failovers_total
from app.services.chain_config import ChainConfig, TokenConfig
from app.services.price_service import PriceService


@dataclass
class AssetBalance:
    symbol: str
    asset_address: str | None
    asset_type: str
    amount: Decimal
    price_usd: Decimal | None
    value_usd: Decimal
    price_source: str | None


@dataclass
class ChainCollectionResult:
    chain: str
    status: str
    native_balance: Decimal | None
    total_usd: Decimal
    rpc_latency_ms: int | None
    balances: list[AssetBalance]
    error_type: str | None = None
    error_message: str | None = None


class RpcAttemptError(RuntimeError):
    def __init__(
        self,
        error_type: str,
        message: str,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.retry_after_seconds = retry_after_seconds


class EvmCollector:
    def __init__(
        self,
        chain_configs: dict[str, ChainConfig],
        price_service: PriceService,
        cooldown_seconds: int = 60,
    ):
        self.chain_configs = chain_configs
        self.price_service = price_service
        self.cooldown_seconds = cooldown_seconds
        self._unavailable_until: dict[str, float] = {}
        self._clients: dict[int, httpx.Client] = {}
        self._validated_chain_ids: set[tuple[str, int]] = set()
        self._token_decimals: dict[tuple[str, str], int] = {}

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def _get_client(self, timeout_seconds: int) -> httpx.Client:
        client = self._clients.get(timeout_seconds)
        if client is None:
            client = httpx.Client(timeout=timeout_seconds)
            self._clients[timeout_seconds] = client
        return client

    def collect_chain(self, address: str, chain: str) -> ChainCollectionResult:
        if not self._is_valid_address(address):
            return self._failed(chain, ErrorType.INVALID_ADDRESS.value, "invalid EVM address")

        config = self.chain_configs.get(chain)
        if config is None:
            return self._failed(chain, ErrorType.UNSUPPORTED_CHAIN.value, "unsupported chain")
        if not config.rpc_urls:
            return self._failed(
                chain,
                ErrorType.MISSING_RPC_URL.value,
                "RPC URL is not configured",
            )

        available = [
            (index, url)
            for index, url in enumerate(config.rpc_urls)
            if self._unavailable_until.get(url, 0) <= monotonic()
        ]
        if not available:
            retry_in = max(
                1,
                int(min(self._unavailable_until[url] for url in config.rpc_urls) - monotonic()),
            )
            return self._failed(
                chain,
                ErrorType.CIRCUIT_OPEN.value,
                f"all RPC endpoints are cooling down; retry in {retry_in}s",
            )

        last_error: RpcAttemptError | None = None
        for position, (provider_index, rpc_url) in enumerate(available):
            started = perf_counter()
            try:
                result = self._collect_from_endpoint(address, config, rpc_url)
            except RpcAttemptError as exc:
                last_error = exc
                cooldown = min(
                    3600,
                    max(1, exc.retry_after_seconds or self.cooldown_seconds),
                )
                self._unavailable_until[rpc_url] = monotonic() + cooldown
                rpc_attempts_total.labels(
                    chain,
                    str(provider_index),
                    "failed",
                    exc.error_type,
                ).inc()
                rpc_circuit_open_total.labels(chain, str(provider_index)).inc()
                if position < len(available) - 1:
                    rpc_failovers_total.labels(chain).inc()
                continue

            result.rpc_latency_ms = int((perf_counter() - started) * 1000)
            self._unavailable_until.pop(rpc_url, None)
            rpc_attempts_total.labels(chain, str(provider_index), "success", "none").inc()
            return result

        assert last_error is not None
        return self._failed(chain, last_error.error_type, str(last_error)[:250])

    def health_check(self) -> dict[str, list[dict[str, str | int]]]:
        results: dict[str, list[dict[str, str | int]]] = {}
        for chain, config in self.chain_configs.items():
            chain_results: list[dict[str, str | int]] = []
            for provider_index, rpc_url in enumerate(config.rpc_urls):
                try:
                    client = self._get_client(config.timeout_seconds)
                    self._verify_chain_id(client, rpc_url, config)
                    chain_results.append(
                        {
                            "provider": provider_index,
                            "status": ChainStatus.SUCCESS.value,
                        }
                    )
                except RpcAttemptError as exc:
                    chain_results.append(
                        {
                            "provider": provider_index,
                            "status": ChainStatus.FAILED.value,
                            "error_type": exc.error_type,
                        }
                    )
            results[chain] = chain_results
        return results

    def _collect_from_endpoint(
        self,
        address: str,
        config: ChainConfig,
        rpc_url: str,
    ) -> ChainCollectionResult:
        client = self._get_client(config.timeout_seconds)
        self._verify_chain_id(client, rpc_url, config)
        wei = self._rpc_int(client, rpc_url, "eth_getBalance", [address, "latest"])
        native_amount = Decimal(wei) / Decimal(10**18)
        native_price, native_source = self.price_service.get_usd_price(config.native_symbol)
        native_value = native_amount * native_price if native_price is not None else Decimal("0")
        balances = [
            AssetBalance(
                symbol=config.native_symbol,
                asset_address=None,
                asset_type=AssetType.NATIVE.value,
                amount=native_amount,
                price_usd=native_price,
                value_usd=native_value,
                price_source=native_source,
            )
        ]
        balances.extend(
            self._collect_token(client, rpc_url, address, token, config.name)
            for token in config.tokens
        )

        return ChainCollectionResult(
            chain=config.name,
            status=ChainStatus.SUCCESS.value,
            native_balance=native_amount,
            total_usd=sum(
                (balance.value_usd for balance in balances),
                Decimal("0"),
            ),
            rpc_latency_ms=None,
            balances=balances,
        )

    def _collect_token(
        self,
        client: httpx.Client,
        rpc_url: str,
        wallet_address: str,
        token: TokenConfig,
        chain: str,
    ) -> AssetBalance:
        decimals_key = (chain, token.address.lower())
        decimals = self._token_decimals.get(decimals_key)
        if decimals is None:
            decimals = self._rpc_int(
                client,
                rpc_url,
                "eth_call",
                [{"to": token.address, "data": "0x313ce567"}, "latest"],
            )
            self._token_decimals[decimals_key] = decimals
        padded_address = wallet_address.lower().removeprefix("0x").rjust(64, "0")
        raw_amount = self._rpc_int(
            client,
            rpc_url,
            "eth_call",
            [
                {"to": token.address, "data": f"0x70a08231{padded_address}"},
                "latest",
            ],
        )
        amount = Decimal(raw_amount) / (Decimal(10) ** decimals)
        price, source = self.price_service.get_usd_price(token.price_symbol)
        value = amount * price if price is not None else Decimal("0")
        return AssetBalance(
            symbol=token.symbol,
            asset_address=token.address,
            asset_type=AssetType.ERC20.value,
            amount=amount,
            price_usd=price,
            value_usd=value,
            price_source=source,
        )

    def _verify_chain_id(
        self,
        client: httpx.Client,
        rpc_url: str,
        config: ChainConfig,
    ) -> None:
        cache_key = (rpc_url, config.expected_chain_id)
        if cache_key in self._validated_chain_ids:
            return
        chain_id = self._rpc_int(client, rpc_url, "eth_chainId", [])
        if chain_id != config.expected_chain_id:
            raise RpcAttemptError(
                ErrorType.BAD_CONFIG.value,
                f"expected chain id {config.expected_chain_id}, got {chain_id}",
            )
        self._validated_chain_ids.add(cache_key)

    def _rpc_int(
        self,
        client: httpx.Client,
        rpc_url: str,
        method: str,
        params: list[object],
    ) -> int:
        result = self._rpc_call(client, rpc_url, method, params)
        try:
            return int(result, 16)
        except (TypeError, ValueError) as exc:
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"invalid {method} result",
            ) from exc

    @staticmethod
    def _rpc_call(
        client: httpx.Client,
        rpc_url: str,
        method: str,
        params: list[object],
    ) -> str:
        try:
            response = client.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            )
            if response.status_code == 429:
                raise RpcAttemptError(
                    ErrorType.RATE_LIMIT.value,
                    "RPC rate limit exceeded",
                    retry_after_seconds=EvmCollector._retry_after_seconds(response),
                )
            response.raise_for_status()
            payload = response.json()
        except RpcAttemptError:
            raise
        except httpx.TimeoutException as exc:
            raise RpcAttemptError(
                ErrorType.TIMEOUT.value,
                "RPC request timed out",
            ) from exc
        except httpx.ConnectError as exc:
            raise RpcAttemptError(
                ErrorType.CONNECTION_ERROR.value,
                "RPC connection failed",
            ) from exc
        except Exception as exc:
            raise RpcAttemptError(ErrorType.RPC_ERROR.value, str(exc)[:250]) from exc

        if payload.get("error") is not None:
            error = str(payload["error"])
            error_type = (
                ErrorType.RATE_LIMIT.value
                if "rate" in error.lower() or "too many" in error.lower()
                else ErrorType.RPC_ERROR.value
            )
            raise RpcAttemptError(error_type, error[:250])
        result = payload.get("result")
        if not isinstance(result, str):
            raise RpcAttemptError(
                ErrorType.RPC_ERROR.value,
                f"RPC response for {method} has no result",
            )
        return result

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> int | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(1, int(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(1, int((retry_at - datetime.now(UTC)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _is_valid_address(address: str | None) -> bool:
        return bool(address and address.startswith("0x") and len(address) == 42)

    @staticmethod
    def _failed(
        chain: str,
        error_type: str,
        error_message: str,
        rpc_latency_ms: int | None = None,
    ) -> ChainCollectionResult:
        return ChainCollectionResult(
            chain=chain,
            status=ChainStatus.FAILED.value,
            native_balance=None,
            total_usd=Decimal("0"),
            rpc_latency_ms=rpc_latency_ms,
            balances=[],
            error_type=error_type,
            error_message=error_message,
        )
