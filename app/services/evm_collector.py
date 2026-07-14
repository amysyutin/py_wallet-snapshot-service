from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter

import httpx

from app.enums import AssetType, ChainStatus, ErrorType
from app.services.chain_config import ChainConfig
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


class EvmCollector:
    def __init__(self, chain_configs: dict[str, ChainConfig], price_service: PriceService):
        self.chain_configs = chain_configs
        self.price_service = price_service

    def collect_chain(self, address: str, chain: str) -> ChainCollectionResult:
        if not self._is_valid_address(address):
            return self._failed(chain, ErrorType.INVALID_ADDRESS.value, "invalid EVM address")

        config = self.chain_configs.get(chain)
        if config is None:
            return self._failed(chain, ErrorType.UNSUPPORTED_CHAIN.value, "unsupported chain")
        if not config.rpc_url:
            return self._failed(chain, ErrorType.MISSING_RPC_URL.value, "RPC URL is not configured")

        started = perf_counter()
        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(
                    config.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getBalance",
                        "params": [address, "latest"],
                        "id": 1,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return self._failed(chain, ErrorType.TIMEOUT.value, "RPC request timed out")
        except httpx.ConnectError:
            return self._failed(chain, ErrorType.CONNECTION_ERROR.value, "RPC connection failed")
        except Exception as exc:
            return self._failed(chain, ErrorType.RPC_ERROR.value, str(exc)[:250])

        latency_ms = int((perf_counter() - started) * 1000)
        if "error" in payload:
            return self._failed(
                chain, ErrorType.RPC_ERROR.value, str(payload["error"])[:250], latency_ms
            )

        wei = int(payload.get("result", "0x0"), 16)
        amount = Decimal(wei) / Decimal(10**18)
        price, source = self.price_service.get_usd_price(config.native_symbol)
        value = amount * price if price is not None else Decimal("0")
        balance = AssetBalance(
            symbol=config.native_symbol,
            asset_address=None,
            asset_type=AssetType.NATIVE.value,
            amount=amount,
            price_usd=price,
            value_usd=value,
            price_source=source,
        )
        return ChainCollectionResult(
            chain=chain,
            status=ChainStatus.SUCCESS.value,
            native_balance=amount,
            total_usd=value,
            rpc_latency_ms=latency_ms,
            balances=[balance],
        )

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
