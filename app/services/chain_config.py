from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class ChainConfig:
    name: str
    native_symbol: str
    rpc_url: str
    timeout_seconds: int


SUPPORTED_CHAINS = ("ethereum", "base", "arbitrum", "bnb", "linea")


def get_chain_configs(settings: Settings) -> dict[str, ChainConfig]:
    return {
        "ethereum": ChainConfig(
            "ethereum", "ETH", settings.ethereum_rpc_url, settings.ethereum_timeout_seconds
        ),
        "base": ChainConfig("base", "ETH", settings.base_rpc_url, settings.chain_timeout_seconds),
        "arbitrum": ChainConfig(
            "arbitrum", "ETH", settings.arbitrum_rpc_url, settings.chain_timeout_seconds
        ),
        "bnb": ChainConfig("bnb", "BNB", settings.bnb_rpc_url, settings.chain_timeout_seconds),
        "linea": ChainConfig("linea", "ETH", settings.linea_rpc_url, settings.chain_timeout_seconds),
    }

