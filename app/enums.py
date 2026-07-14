from enum import Enum


class TriggerType(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RETRY = "retry"


class ScopeType(str, Enum):
    ALL = "all"
    GROUP = "group"
    WALLET = "wallet"
    FAILED_CHAINS = "failed_chains"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WalletSnapshotStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ChainStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class WalletType(str, Enum):
    EVM = "evm"
    MANUAL = "manual"


class AssetType(str, Enum):
    NATIVE = "native"
    ERC20 = "erc20"
    MANUAL = "manual"


class ErrorType(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RPC_ERROR = "rpc_error"
    CONNECTION_ERROR = "connection_error"
    INVALID_ADDRESS = "invalid_address"
    UNSUPPORTED_CHAIN = "unsupported_chain"
    MISSING_RPC_URL = "missing_rpc_url"
    PRICE_UNAVAILABLE = "price_unavailable"
    BAD_CONFIG = "bad_config"
    UNKNOWN = "unknown"
