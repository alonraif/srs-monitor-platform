from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass(frozen=True)
class PublisherIpRecord:
    ip: str
    updated_at: datetime


_CACHE_TTL = timedelta(hours=6)
_lock = Lock()
_records: dict[str, PublisherIpRecord] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().strip("/").lower()


def _purge_expired(now: datetime) -> None:
    expired = [key for key, item in _records.items() if now - item.updated_at > _CACHE_TTL]
    for key in expired:
        _records.pop(key, None)


def remember_publish_ip(*, ip: str | None, app: str | None, stream: str | None, stream_id: str | None) -> None:
    ip_value = (ip or "").strip()
    if not ip_value:
        return

    keys = {
        _normalize_key(stream_id),
        _normalize_key(stream),
        _normalize_key(f"{_normalize_key(app)}/{_normalize_key(stream)}"),
    }
    keys.discard("")
    if not keys:
        return

    now = _now()
    with _lock:
        _purge_expired(now)
        record = PublisherIpRecord(ip=ip_value, updated_at=now)
        for key in keys:
            _records[key] = record


def resolve_publish_ip(*, app: str | None, stream: str | None, stream_id: str | None) -> str | None:
    candidates = [
        _normalize_key(stream_id),
        _normalize_key(stream),
        _normalize_key(f"{_normalize_key(app)}/{_normalize_key(stream)}"),
    ]
    now = _now()
    with _lock:
        _purge_expired(now)
        for key in candidates:
            if not key:
                continue
            match = _records.get(key)
            if match:
                return match.ip
    return None
