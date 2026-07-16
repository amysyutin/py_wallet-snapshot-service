from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class TokenConfig:
    symbol: str
    address: str
    price_symbol: str = "USDC"


@dataclass(frozen=True)
class ChainConfig:
    name: str
    native_symbol: str
    expected_chain_id: int
    rpc_urls: tuple[str, ...]
    timeout_seconds: int
    tokens: tuple[TokenConfig, ...] = ()

    @property
    def rpc_url(self) -> str:
        return self.rpc_urls[0] if self.rpc_urls else ""


SUPPORTED_CHAINS = ("mainnet", "base", "arbitrum", "bnb", "linea")

TOKENS_BY_CHAIN: dict[str, tuple[TokenConfig, ...]] = {
    "mainnet": (TokenConfig("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),),
    "base": (
        TokenConfig("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
        TokenConfig("USDbC", "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"),
    ),
    "arbitrum": (
        TokenConfig("USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"),
        TokenConfig("USDC.e", "0xFF970A61A04b1cA14834A43f5de4533eBDDB5CC8"),
    ),
    "bnb": (
        TokenConfig(
            "BINANCE_PEG_USDC",
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        ),
    ),
    "linea": (TokenConfig("USDC", "0x176211869cA2b568f2A7D4EE941E073a821EE1ff"),),
}


def _rpc_urls(value: str) -> tuple[str, ...]:
    return tuple(url.strip() for url in value.split(",") if url.strip())


def get_enabled_chains(settings: Settings) -> tuple[str, ...]:
    requested = tuple(
        chain.strip() for chain in settings.snapshot_enabled_chains.split(",") if chain.strip()
    )
    return tuple(chain for chain in requested if chain in SUPPORTED_CHAINS) or SUPPORTED_CHAINS


def get_chain_configs(settings: Settings) -> dict[str, ChainConfig]:
    return {
        "mainnet": ChainConfig(
            "mainnet",
            "ETH",
            1,
            _rpc_urls(settings.ethereum_rpc_url),
            settings.ethereum_timeout_seconds,
            TOKENS_BY_CHAIN["mainnet"],
        ),
        "base": ChainConfig(
            "base",
            "ETH",
            8453,
            _rpc_urls(settings.base_rpc_url),
            settings.chain_timeout_seconds,
            TOKENS_BY_CHAIN["base"],
        ),
        "arbitrum": ChainConfig(
            "arbitrum",
            "ETH",
            42161,
            _rpc_urls(settings.arbitrum_rpc_url),
            settings.chain_timeout_seconds,
            TOKENS_BY_CHAIN["arbitrum"],
        ),
        "bnb": ChainConfig(
            "bnb",
            "BNB",
            56,
            _rpc_urls(settings.bnb_rpc_url),
            settings.chain_timeout_seconds,
            TOKENS_BY_CHAIN["bnb"],
        ),
        "linea": ChainConfig(
            "linea",
            "ETH",
            59144,
            _rpc_urls(settings.linea_rpc_url),
            settings.chain_timeout_seconds,
            TOKENS_BY_CHAIN["linea"],
        ),
    }
