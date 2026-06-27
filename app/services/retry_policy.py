from app.enums import ErrorType

TEMPORARY_ERRORS = {
    ErrorType.TIMEOUT.value,
    ErrorType.RATE_LIMIT.value,
    ErrorType.CONNECTION_ERROR.value,
    ErrorType.RPC_ERROR.value,
}

PERMANENT_ERRORS = {
    ErrorType.INVALID_ADDRESS.value,
    ErrorType.UNSUPPORTED_CHAIN.value,
    ErrorType.MISSING_RPC_URL.value,
    ErrorType.BAD_CONFIG.value,
}


def should_retry(error_type: str | None) -> bool:
    return bool(error_type and error_type in TEMPORARY_ERRORS and error_type not in PERMANENT_ERRORS)

