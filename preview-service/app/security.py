from os import getenv

from fastapi import Header, HTTPException, status


PREVIEW_AUTH_TOKEN = getenv("PREVIEW_AUTH_TOKEN", "").strip()


def require_preview_token(authorization: str | None = Header(default=None)) -> None:
    if not PREVIEW_AUTH_TOKEN:
        return
    expected = f"Bearer {PREVIEW_AUTH_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
