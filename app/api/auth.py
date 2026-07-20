import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    expected_token = get_settings().internal_api_token
    token_matches = x_internal_token is not None and secrets.compare_digest(
        x_internal_token.encode("utf-8"), expected_token.encode("utf-8")
    )
    if not token_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token"
        )
