from functools import lru_cache
from os import getenv

from pydantic import BaseModel


def _env_bool(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    value = getenv(name)
    if value is None:
        return default
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def _env_int(name: str, default: int) -> int:
    value = getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_regex(name: str, default: str) -> str:
    value = getenv(name)
    if value is None:
        return default
    # .env values are commonly over-escaped (e.g. "\\d" instead of "\d").
    # Normalize to avoid unexpected CORS regex mismatches.
    return value.replace("\\\\", "\\")


class Settings(BaseModel):
    service_name: str = "monitor-backend"
    version: str = "0.1.0"
    mock_mode: bool = _env_bool("MOCK_MODE", True)
    srs_api_url: str = getenv("SRS_API_URL", "http://srs:1985")
    srs_api_timeout_seconds: float = _env_float("SRS_API_TIMEOUT_SECONDS", 2.5)
    srs_public_http_base_url: str = getenv("SRS_PUBLIC_HTTP_BASE_URL", "http://localhost:8080")
    srs_internal_http_base_url: str = getenv("SRS_INTERNAL_HTTP_BASE_URL", "http://srs:8080")
    srs_public_webrtc_base_url: str = getenv("SRS_PUBLIC_WEBRTC_BASE_URL", "webrtc://localhost")
    preview_preferred_protocol: str = getenv("PREVIEW_PREFERRED_PROTOCOL", "webrtc")
    preview_force_rewrap: bool = _env_bool("PREVIEW_FORCE_REWRAP", False)
    preview_public_base_url: str = getenv("PREVIEW_PUBLIC_BASE_URL", "http://localhost:8001")
    preview_service_url: str = getenv("PREVIEW_SERVICE_URL", "http://preview-service:8001")
    preview_auth_token: str = getenv("PREVIEW_AUTH_TOKEN", "")
    backend_api_auth_enabled: bool = _env_bool("BACKEND_API_AUTH_ENABLED", False)
    backend_read_api_key: str = getenv("BACKEND_READ_API_KEY", "")
    backend_write_api_key: str = getenv("BACKEND_WRITE_API_KEY", "")
    srs_api_username: str = getenv("SRS_API_USERNAME", "")
    srs_api_password: str = getenv("SRS_API_PASSWORD", "")
    srs_hook_shared_secret: str = getenv("SRS_HOOK_SHARED_SECRET", "")
    stream_auth_enforce: bool = _env_bool("STREAM_AUTH_ENFORCE", False)
    stream_auth_secret: str = getenv("STREAM_AUTH_SECRET", "")
    stream_auth_clock_skew_seconds: int = _env_int("STREAM_AUTH_CLOCK_SKEW_SECONDS", 60)
    cors_allow_origins: list[str] = _env_list(
        "CORS_ALLOW_ORIGINS",
        ["http://localhost:3000", "http://127.0.0.1:3000"],
    )
    cors_allow_origin_regex: str = _env_regex(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"^https?://(localhost|127\\.0\\.0\\.1|10\\.\\d+\\.\\d+\\.\\d+|172\\.(1[6-9]|2\\d|3[0-1])\\.\\d+\\.\\d+|192\\.168\\.\\d+\\.\\d+)(:\\d+)?$",
    )
    sqlite_path: str = getenv("SQLITE_PATH", "/data/monitor.db")
    ffprobe_enabled: bool = _env_bool("FFPROBE_ENABLED", True)
    ffprobe_timeout_seconds: float = _env_float("FFPROBE_TIMEOUT_SECONDS", 2.5)
    ffprobe_cache_ttl_seconds: float = _env_float("FFPROBE_CACHE_TTL_SECONDS", 10.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
