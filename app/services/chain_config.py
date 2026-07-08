from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class ChainConfig:
    name: str
    native_symbol: str
    rpc_url: str
    timeout_seconds: int


SUPPORTED_CHAINS = ("mainnet", "base", "arbitrum", "bnb", "linea")


def get_enabled_chains(settings: Settings) -> tuple[str, ...]:
    requested = tuple(
        chain.strip() for chain in settings.snapshot_enabled_chains.split(",") if chain.strip()
    )
    return tuple(chain for chain in requested if chain in SUPPORTED_CHAINS) or SUPPORTED_CHAINS


def get_chain_configs(settings: Settings) -> dict[str, ChainConfig]:
    return {
        "mainnet": ChainConfig(
            "mainnet", "ETH", settings.ethereum_rpc_url, settings.ethereum_timeout_seconds
        ),
        "base": ChainConfig("base", "ETH", settings.base_rpc_url, settings.chain_timeout_seconds),
        "arbitrum": ChainConfig(
            "arbitrum", "ETH", settings.arbitrum_rpc_url, settings.chain_timeout_seconds
        ),
        "bnb": ChainConfig("bnb", "BNB", settings.bnb_rpc_url, settings.chain_timeout_seconds),
        "linea": ChainConfig(
            "linea", "ETH", settings.linea_rpc_url, settings.chain_timeout_seconds
        ),
    }
