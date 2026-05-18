import hashlib
import hmac
import ipaddress
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qs

from .config import get_settings
from .models import ExpectedStreamRecord
from .repositories.expected_streams import ExpectedStreamsRepository


logger = logging.getLogger("stream-auth")


@dataclass(frozen=True)
class StreamAuthDecision:
    allow: bool
    reason: str
    stream_id: str
    action: Literal["publish", "play"]
    report_only: bool


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _stream_id_from_payload(payload: dict[str, Any]) -> str:
    app = _as_str(payload.get("app")).strip("/")
    stream = _as_str(payload.get("stream")).strip("/")
    if app and stream:
        return f"{app}/{stream}"
    if stream:
        return stream
    return _as_str(payload.get("stream_url")).strip("/")


def _extract_params(payload: dict[str, Any]) -> dict[str, str]:
    raw = _as_str(payload.get("param"))
    if raw.startswith("?"):
        raw = raw[1:]
    data = parse_qs(raw, keep_blank_values=False)
    result: dict[str, str] = {}
    for key, values in data.items():
        if values:
            result[key] = values[-1]
    return result


def _source_ip(payload: dict[str, Any]) -> str:
    return _as_str(payload.get("ip") or payload.get("client_ip"))


def _in_allowed_cidrs(source_ip: str, raw_cidrs: str, fallback_cidr: str) -> bool:
    ip_txt = source_ip.strip()
    if not ip_txt:
        return False
    try:
        source = ipaddress.ip_address(ip_txt)
    except ValueError:
        return False

    cidrs: list[str] = []
    cidrs.extend([x.strip() for x in raw_cidrs.split(",") if x.strip()])
    if not cidrs and fallback_cidr and fallback_cidr.lower() != "unknown":
        cidrs = [fallback_cidr.strip()]
    if not cidrs:
        return True

    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if source in net:
            return True
    return False


def _verify_signed_token(action: str, stream_id: str, params: dict[str, str]) -> tuple[bool, str]:
    settings = get_settings()
    secret = settings.stream_auth_secret.strip()
    if not secret:
        return False, "stream_auth_secret_missing"

    token = (params.get("token") or params.get("sig") or "").strip()
    exp_raw = (params.get("exp") or "").strip()
    if not token or not exp_raw:
        return False, "token_or_exp_missing"
    try:
        exp = int(exp_raw)
    except ValueError:
        return False, "exp_invalid"

    now = int(datetime.now(UTC).timestamp())
    if exp + settings.stream_auth_clock_skew_seconds < now:
        return False, "token_expired"

    signing = f"{action}|{stream_id}|{exp}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signing, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, token):
        return False, "token_invalid"
    return True, "ok"


def evaluate_stream_auth(payload: dict[str, Any], action: Literal["publish", "play"]) -> StreamAuthDecision:
    settings = get_settings()
    repository = ExpectedStreamsRepository()
    stream_id = _stream_id_from_payload(payload)
    src_ip = _source_ip(payload)
    params = _extract_params(payload)

    expected = repository.get_by_stream_id(stream_id)
    if expected is None:
        deny_reason = "stream_not_expected"
        return _decision(stream_id, action, deny_reason, False)

    allow, reason = _evaluate_against_expected(expected, action, src_ip, params)
    return _decision(stream_id, action, reason, allow)


def _evaluate_against_expected(
    expected: ExpectedStreamRecord,
    action: Literal["publish", "play"],
    source_ip: str,
    params: dict[str, str],
) -> tuple[bool, str]:
    if not expected.auth_required or expected.auth_mode == "disabled":
        return True, "auth_disabled"

    cidr_policy = expected.allowed_publish_cidrs if action == "publish" else expected.allowed_play_cidrs
    cidr_ok = _in_allowed_cidrs(source_ip, cidr_policy, expected.expected_source_ip_or_cidr)
    if not cidr_ok:
        return False, "source_ip_not_allowed"

    if expected.auth_mode == "ip_only":
        return True, "ip_only_allowed"

    if expected.token_required:
        token_ok, reason = _verify_signed_token(action, expected.stream_id, params)
        if not token_ok:
            return False, reason

    return True, "authorized"


def _decision(stream_id: str, action: Literal["publish", "play"], reason: str, allow: bool) -> StreamAuthDecision:
    settings = get_settings()
    enforced_allow = allow or not settings.stream_auth_enforce
    report_only = not settings.stream_auth_enforce

    logger.info(
        "srs_hook_decision action=%s stream_id=%s allow=%s enforced_allow=%s report_only=%s reason=%s",
        action,
        stream_id,
        allow,
        enforced_allow,
        report_only,
        reason,
    )
    return StreamAuthDecision(
        allow=enforced_allow,
        reason=reason,
        stream_id=stream_id,
        action=action,
        report_only=report_only,
    )


def hook_response(decision: StreamAuthDecision) -> int:
    # SRS expects body integer where 0 = allow.
    return 0 if decision.allow else 403


def mint_stream_token(action: Literal["publish", "play"], stream_id: str, exp: int) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.stream_auth_secret.strip()
    if not secret:
        raise ValueError("stream_auth_secret_missing")
    signing = f"{action}|{stream_id}|{exp}".encode("utf-8")
    token = hmac.new(secret.encode("utf-8"), signing, hashlib.sha256).hexdigest()
    return {"action": action, "stream_id": stream_id, "exp": exp, "token": token}


def pretty_hook_payload(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, sort_keys=True)
    except Exception:
        return str(payload)
