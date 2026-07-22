from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "development", "test", "staging", "production"]
SECURE_ENVIRONMENTS = frozenset({"staging", "production"})
INSECURE_INTERNAL_API_TOKENS = frozenset(
    {"change-me", "changeme", "password", "secret", "test-token"}
)
MIN_PRODUCTION_TOKEN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "py-wallet-snapshot-service"
    app_version: str = "0.1.0"
    build_sha: str = "unknown"
    environment: Environment = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://user:password@localhost:5432/py_wallet"
    internal_api_token: str = ""

    snapshot_service_host: str = "0.0.0.0"
    snapshot_service_port: int = 8001

    snapshot_worker_enabled: bool = True
    snapshot_scheduler_enabled: bool = True
    snapshot_interval_seconds: int = 300
    snapshot_worker_poll_seconds: int = 5
    snapshot_job_lease_seconds: int = Field(default=1800, ge=60, le=86400)
    snapshot_enabled_chains: str = "mainnet,base,arbitrum,bnb,linea"
    debug_endpoints_enabled: bool = True

    chain_timeout_seconds: int = 8
    ethereum_timeout_seconds: int = 10
    rpc_cooldown_seconds: int = 60
    rpc_startup_check_enabled: bool = True

    ethereum_rpc_url: str = ""
    base_rpc_url: str = ""
    arbitrum_rpc_url: str = ""
    bnb_rpc_url: str = ""
    linea_rpc_url: str = ""

    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    price_cache_ttl_seconds: int = 60

    max_retry_attempts: int = 3
    retry_backoff_seconds: str = Field(default="0,30,120")

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_internal_api_token(self) -> Self:
        token = self.internal_api_token
        if not token or not token.strip():
            raise ValueError("INTERNAL_API_TOKEN is required")
        if token != token.strip():
            raise ValueError("INTERNAL_API_TOKEN must not contain surrounding whitespace")
        if self.environment in SECURE_ENVIRONMENTS:
            if token.lower() in INSECURE_INTERNAL_API_TOKENS:
                raise ValueError("INTERNAL_API_TOKEN cannot use a known placeholder")
            if len(token) < MIN_PRODUCTION_TOKEN_LENGTH:
                raise ValueError(
                    "INTERNAL_API_TOKEN must be at least "
                    f"{MIN_PRODUCTION_TOKEN_LENGTH} characters in staging or production"
                )
        return self

    @property
    def retry_backoff_schedule(self) -> list[int]:
        return [int(part.strip()) for part in self.retry_backoff_seconds.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
