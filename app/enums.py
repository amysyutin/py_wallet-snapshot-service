from enum import StrEnum


class TriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RETRY = "retry"


class ScopeType(StrEnum):
    ALL = "all"
    GROUP = "group"
    WALLET = "wallet"
    FAILED_CHAINS = "failed_chains"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WalletSnapshotStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ChainStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class WalletType(StrEnum):
    EVM = "evm"
    MANUAL = "manual"


class AssetType(StrEnum):
    NATIVE = "native"
    ERC20 = "erc20"
    MANUAL = "manual"


class ErrorType(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_OPEN = "circuit_open"
    RPC_ERROR = "rpc_error"
    CONNECTION_ERROR = "connection_error"
    INVALID_ADDRESS = "invalid_address"
    UNSUPPORTED_CHAIN = "unsupported_chain"
    MISSING_RPC_URL = "missing_rpc_url"
    PRICE_UNAVAILABLE = "price_unavailable"
    BAD_CONFIG = "bad_config"
    UNKNOWN = "unknown"
