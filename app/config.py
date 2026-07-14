from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "py-wallet-snapshot-service"
    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://user:password@localhost:5432/py_wallet"
    internal_api_token: str = "change-me"

    snapshot_service_host: str = "0.0.0.0"
    snapshot_service_port: int = 8001

    snapshot_worker_enabled: bool = True
    snapshot_scheduler_enabled: bool = True
    snapshot_interval_seconds: int = 300
    snapshot_worker_poll_seconds: int = 5
    snapshot_enabled_chains: str = "mainnet,base,arbitrum,bnb,linea"
    debug_endpoints_enabled: bool = True

    chain_timeout_seconds: int = 8
    ethereum_timeout_seconds: int = 10

    ethereum_rpc_url: str = ""
    base_rpc_url: str = ""
    arbitrum_rpc_url: str = ""
    bnb_rpc_url: str = ""
    linea_rpc_url: str = ""

    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    price_cache_ttl_seconds: int = 60

    max_retry_attempts: int = 3
    retry_backoff_seconds: str = Field(default="0,30,120")

    @property
    def retry_backoff_schedule(self) -> list[int]:
        return [int(part.strip()) for part in self.retry_backoff_seconds.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
