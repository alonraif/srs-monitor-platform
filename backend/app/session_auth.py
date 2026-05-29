import secrets
from datetime import datetime, timezone
from threading import Lock

from fastapi import HTTPException, Request, status

from .config import get_settings

SESSION_HEADER = "x-session-token"


class SessionStore:
    def __init__(self) -> None:
        self._tokens: dict[str, datetime] = {}
        self._lock = Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        with self._lock:
            self._tokens[token] = now
        return token

    def touch_if_valid(self, token: str) -> bool:
        if not token:
            return False
        now = datetime.now(timezone.utc)
        with self._lock:
            if token not in self._tokens:
                return False
            self._tokens[token] = now
        return True

    def delete(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._tokens.pop(token, None)


session_store = SessionStore()


def ui_auth_enabled() -> bool:
    return bool(get_settings().ui_login_password.strip())


def verify_password(password: str) -> bool:
    expected = get_settings().ui_login_password
    return bool(expected) and secrets.compare_digest(password, expected)


def _extract_session_token(request: Request) -> str:
    return request.headers.get(SESSION_HEADER, "").strip()


def enforce_ui_session_auth(request: Request) -> None:
    if not ui_auth_enabled():
        return

    path = request.url.path
    if not path.startswith("/api"):
        return
    if request.method == "OPTIONS":
        return

    if path in {"/api/health", "/api/live", "/api/auth/login", "/api/auth/logout", "/api/auth/session"}:
        return

    token = _extract_session_token(request)
    if not session_store.touch_if_valid(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )


def extract_session_token(request: Request) -> str:
    return _extract_session_token(request)
