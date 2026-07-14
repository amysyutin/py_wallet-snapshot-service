from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if x_internal_token != get_settings().internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token"
        )
