from fastapi import HTTPException, Request, status

from .config import get_settings


SAFE_METHODS = {"GET", "HEAD"}


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    x_api_key = request.headers.get("x-api-key", "").strip()
    return x_api_key or None


def enforce_backend_api_auth(request: Request) -> None:
    settings = get_settings()
    if not settings.backend_api_auth_enabled:
        return

    path = request.url.path
    if not path.startswith("/api"):
        return
    if request.method == "OPTIONS":
        # Let CORS preflight pass without API keys.
        return
    if path in {"/api/health", "/api/live"}:
        return

    provided = _extract_api_key(request)
    if request.method in SAFE_METHODS:
        required = settings.backend_read_api_key
    else:
        required = settings.backend_write_api_key or settings.backend_read_api_key

    if not required:
        # Fail closed if auth is enabled but keys are not configured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="backend_api_auth_misconfigured",
        )

    if provided != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
