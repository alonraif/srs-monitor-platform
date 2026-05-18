from datetime import UTC, datetime
from ipaddress import ip_address, ip_network

from .config import get_settings
from .mock_data import get_clients, get_streams, get_system
from .models import (
    Alarm,
    AlarmSeverity,
    AlarmStatus,
    AlarmsResponse,
    Client,
    ExpectedStreamRecord,
    HealthResponse,
    HostHealth,
    IngestStream,
    ServiceState,
)
from .normalizer import (
    normalize_clients,
    normalize_health,
    normalize_streams,
    normalize_system,
)
from .repositories.alarms import AlarmsRepository
from .repositories.expected_streams import ExpectedStreamsRepository
from .srs_client import fetch_srs_snapshot


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class AlarmEngine:
    def __init__(self) -> None:
        self._alarms_repo = AlarmsRepository()
        self._expected_repo = ExpectedStreamsRepository()
        # Avoid UI alarm flicker from one-off telemetry misses by requiring
        # alarms to be absent for a short grace window before resolving.
        self._resolve_grace_seconds = 9

    async def evaluate_and_list(self) -> AlarmsResponse:
        now = _now()
        health, streams, clients, host = await self._current_inputs()
        expected = self._expected_repo.list_streams().streams

        desired = self._evaluate_rules(now, health, streams, clients, host, expected)
        active = self._reconcile_runtime(desired, now)
        return AlarmsResponse(
            generated_at=now,
            total=len(active),
            active=sum(alarm.status == AlarmStatus.ACTIVE for alarm in active),
            critical=sum(alarm.severity == AlarmSeverity.CRITICAL for alarm in active),
            alarms=active,
        )

    async def acknowledge(self, alarm_id: str, actor: str) -> Alarm | None:
        changed = self._alarms_repo.set_acknowledged(alarm_id, acknowledged=True, acknowledged_by=actor)
        if not changed:
            return None
        alarm = self._alarms_repo.get_runtime(alarm_id)
        if alarm is None:
            return None
        self._alarms_repo.append_history(
            alarm_id=alarm.id,
            action="acknowledged",
            severity=alarm.severity.value,
            status=alarm.status.value,
            message=alarm.title,
            actor=actor,
            metadata={"description": alarm.description},
        )
        return alarm

    async def unacknowledge(self, alarm_id: str, actor: str) -> Alarm | None:
        changed = self._alarms_repo.set_acknowledged(alarm_id, acknowledged=False, acknowledged_by=actor)
        if not changed:
            return None
        alarm = self._alarms_repo.get_runtime(alarm_id)
        if alarm is None:
            return None
        self._alarms_repo.append_history(
            alarm_id=alarm.id,
            action="unacknowledged",
            severity=alarm.severity.value,
            status=alarm.status.value,
            message=alarm.title,
            actor=actor,
            metadata={"description": alarm.description},
        )
        return alarm

    async def _current_inputs(self) -> tuple[HealthResponse, list[IngestStream], list[Client], HostHealth]:
        settings = get_settings()
        if settings.mock_mode:
            health = normalize_health(None)
            system = get_system()
            return health, get_streams(), get_clients(), system.host

        snapshot = await fetch_srs_snapshot()
        health = normalize_health(snapshot)
        system = normalize_system(snapshot)
        return health, normalize_streams(snapshot), normalize_clients(snapshot), system.host

    def _evaluate_rules(
        self,
        now: datetime,
        health: HealthResponse,
        streams: list[IngestStream],
        clients: list[Client],
        host: HostHealth,
        expected_streams: list[ExpectedStreamRecord],
    ) -> dict[str, Alarm]:
        alarms: dict[str, Alarm] = {}
        stream_map: dict[str, IngestStream] = {}
        canonical_by_expected_id: dict[str, str] = {}
        for stream in streams:
            for token in self._stream_match_tokens(stream):
                if token not in stream_map:
                    stream_map[token] = stream

        clients_by_stream: dict[str, int] = {}
        for client in clients:
            if client.stream_id:
                clients_by_stream[client.stream_id] = clients_by_stream.get(client.stream_id, 0) + 1

        if health.health_state == ServiceState.SRS_UNREACHABLE:
            alarms["srs_unreachable"] = self._make_alarm(
                now,
                alarm_id="srs_unreachable",
                severity=AlarmSeverity.CRITICAL,
                stream_id=None,
                title="SRS API Unreachable",
                description=f"Backend cannot reach SRS API at {health.srs_api_url}",
            )

        mem_percent = self._host_metric_percent(host, "memory")
        disk_percent = self._host_metric_percent(host, "disk")
        if host.cpu_percent >= 90:
            alarms["cpu_high"] = self._make_alarm(now, "cpu_high", AlarmSeverity.CRITICAL, None, "CPU High", f"Host CPU at {host.cpu_percent:.1f}%")
        if mem_percent >= 90:
            alarms["memory_high"] = self._make_alarm(now, "memory_high", AlarmSeverity.CRITICAL, None, "Memory High", f"Host memory at {mem_percent:.1f}%")
        if disk_percent >= 90:
            alarms["disk_high"] = self._make_alarm(now, "disk_high", AlarmSeverity.WARNING, None, "Disk High", f"Host disk at {disk_percent:.1f}%")
        if host.uptime_seconds > 0 and host.uptime_seconds < 300:
            alarms["container_restart"] = self._make_alarm(
                now,
                "container_restart",
                AlarmSeverity.WARNING,
                None,
                "Container Restart Detected",
                f"Host uptime is only {host.uptime_seconds} seconds",
            )

        for expected in expected_streams:
            stream = stream_map.get(expected.stream_id)
            if stream is not None:
                canonical_by_expected_id[expected.stream_id] = stream.id
            canonical_stream_id = canonical_by_expected_id.get(expected.stream_id, expected.stream_id)
            client_count = clients_by_stream.get(canonical_stream_id, 0)

            if stream is None or stream.status == "offline":
                alarms[f"stream_offline:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"stream_offline:{expected.stream_id}",
                    AlarmSeverity.CRITICAL,
                    expected.stream_id,
                    "Expected Stream Offline",
                    f"Expected stream '{expected.stream_id}' is missing or offline",
                )
                continue

            bitrate = stream.metrics.bitrate_kbps
            expected_protocol = (expected.expected_protocol or "").strip().lower()
            actual_protocol = str(stream.protocol.value).strip().lower()
            if expected_protocol not in {"", "unknown"} and actual_protocol != expected_protocol:
                alarms[f"protocol_mismatch:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"protocol_mismatch:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Protocol Mismatch",
                    f"Expected protocol {expected.expected_protocol} but observed {stream.protocol.value}",
                )

            expected_resolution = (expected.expected_resolution or "").strip().lower()
            actual_resolution = (stream.metrics.resolution or "").strip().lower()
            if expected_resolution not in {"", "unknown"} and actual_resolution not in {"", "unknown"} and actual_resolution != expected_resolution:
                alarms[f"resolution_mismatch:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"resolution_mismatch:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Resolution Mismatch",
                    f"Expected resolution {expected.expected_resolution} but observed {stream.metrics.resolution}",
                )

            if expected.expected_fps is not None and stream.metrics.fps is not None:
                # Allow small jitter/timing variance around nominal frame-rates.
                if abs(float(stream.metrics.fps) - float(expected.expected_fps)) > 0.5:
                    alarms[f"fps_mismatch:{expected.stream_id}"] = self._make_alarm(
                        now,
                        f"fps_mismatch:{expected.stream_id}",
                        AlarmSeverity.WARNING,
                        expected.stream_id,
                        "FPS Mismatch",
                        f"Expected FPS {expected.expected_fps} but observed {stream.metrics.fps:.2f}",
                    )

            if expected.expected_min_bitrate is not None and bitrate is not None and bitrate < expected.expected_min_bitrate:
                alarms[f"bitrate_too_low:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"bitrate_too_low:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Bitrate Too Low",
                    f"Bitrate {bitrate} kbps below expected minimum {expected.expected_min_bitrate} kbps",
                )
            if expected.expected_max_bitrate is not None and bitrate is not None and bitrate > expected.expected_max_bitrate:
                alarms[f"bitrate_too_high:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"bitrate_too_high:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Bitrate Too High",
                    f"Bitrate {bitrate} kbps above expected maximum {expected.expected_max_bitrate} kbps",
                )

            if not self._source_ip_matches(expected.expected_source_ip_or_cidr, stream.source_ip):
                alarms[f"unexpected_source_ip:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"unexpected_source_ip:{expected.stream_id}",
                    AlarmSeverity.CRITICAL,
                    expected.stream_id,
                    "Unexpected Source IP",
                    f"Observed source {stream.source_ip} does not match expected {expected.expected_source_ip_or_cidr}",
                )

            # Encryption is not explicitly reported by SRS stream stats. We
            # assume SRT ingest as encrypted and other protocols as not guaranteed.
            if expected.encryption_required and stream.protocol.value != "SRT":
                alarms[f"encryption_required_missing:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"encryption_required_missing:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Encryption Requirement Missing",
                    f"Expected encrypted ingest but observed protocol {stream.protocol.value}",
                )

            if client_count == 0:
                alarms[f"no_clients:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"no_clients:{expected.stream_id}",
                    AlarmSeverity.INFO,
                    expected.stream_id,
                    "No Clients Connected",
                    "No active clients for expected stream",
                )
            if client_count > 5000:
                alarms[f"too_many_clients:{expected.stream_id}"] = self._make_alarm(
                    now,
                    f"too_many_clients:{expected.stream_id}",
                    AlarmSeverity.WARNING,
                    expected.stream_id,
                    "Too Many Clients",
                    f"{client_count} clients exceed threshold 5000",
                )

        return alarms

    def _stream_match_tokens(self, stream: IngestStream) -> set[str]:
        tokens: set[str] = set()
        stream_id = (stream.id or "").strip()
        stream_key = (stream.stream_key or "").strip()
        app = (stream.app or "").strip()
        if stream_id:
            tokens.add(stream_id)
        if stream_key:
            tokens.add(stream_key)
        if app and stream_key:
            tokens.add(f"{app}/{stream_key}")
        parts = [part for part in stream_id.split("/") if part]
        if parts:
            tokens.add(parts[-1])
        if len(parts) >= 2:
            tokens.add(f"{parts[-2]}/{parts[-1]}")
        return tokens

    def _reconcile_runtime(self, desired: dict[str, Alarm], now: datetime) -> list[Alarm]:
        runtime = {alarm.id: alarm for alarm in self._alarms_repo.list_runtime()}
        output: list[Alarm] = []

        for alarm_id, candidate in desired.items():
            existing = runtime.get(alarm_id)
            if existing is None:
                alarm = candidate
                self._alarms_repo.upsert_runtime(alarm)
                self._alarms_repo.append_history(
                    alarm_id=alarm.id,
                    action="activated",
                    severity=alarm.severity.value,
                    status=alarm.status.value,
                    message=alarm.title,
                    metadata={"description": alarm.description},
                )
                output.append(alarm)
                continue

            ack_state = self._alarms_repo.get_ack_state(alarm_id)
            status = AlarmStatus.ACKNOWLEDGED if (ack_state and ack_state["acknowledged"]) else AlarmStatus.ACTIVE
            alarm = Alarm(
                id=alarm_id,
                severity=candidate.severity,
                status=status,
                stream_id=candidate.stream_id,
                title=candidate.title,
                description=candidate.description,
                first_seen=existing.first_seen,
                last_seen=now,
                resolved_at=None,
                acknowledged_by=ack_state["acknowledged_by"] if ack_state else None,
                acknowledged_at=ack_state["acknowledged_at"] if ack_state else None,
            )
            self._alarms_repo.upsert_runtime(alarm)
            output.append(alarm)

        for alarm_id, existing in runtime.items():
            if alarm_id in desired:
                continue
            age_since_last_seen = (now - existing.last_seen).total_seconds()
            if age_since_last_seen < self._resolve_grace_seconds:
                output.append(existing)
                continue
            resolved = Alarm(
                id=alarm_id,
                severity=existing.severity,
                status=AlarmStatus.RESOLVED,
                stream_id=existing.stream_id,
                title=existing.title,
                description=existing.description,
                first_seen=existing.first_seen,
                last_seen=now,
                resolved_at=now,
                acknowledged_by=existing.acknowledged_by,
                acknowledged_at=existing.acknowledged_at,
            )
            self._alarms_repo.append_history(
                alarm_id=resolved.id,
                action="resolved",
                severity=resolved.severity.value,
                status=resolved.status.value,
                message=resolved.title,
                metadata={"description": resolved.description},
            )
            self._alarms_repo.delete_runtime(alarm_id)

        return sorted(output, key=lambda alarm: (alarm.severity.value, alarm.first_seen), reverse=True)

    def _make_alarm(
        self,
        now: datetime,
        alarm_id: str,
        severity: AlarmSeverity,
        stream_id: str | None,
        title: str,
        description: str,
    ) -> Alarm:
        return Alarm(
            id=alarm_id,
            severity=severity,
            status=AlarmStatus.ACTIVE,
            stream_id=stream_id,
            title=title,
            description=description,
            first_seen=now,
            last_seen=now,
            resolved_at=None,
            acknowledged_by=None,
            acknowledged_at=None,
        )

    def _source_ip_matches(self, expected_ip_or_cidr: str, actual_ip: str) -> bool:
        if expected_ip_or_cidr in {"", "unknown"}:
            return True
        try:
            if "/" in expected_ip_or_cidr:
                return ip_address(actual_ip) in ip_network(expected_ip_or_cidr, strict=False)
            return ip_address(actual_ip) == ip_address(expected_ip_or_cidr)
        except ValueError:
            return False

    def _host_metric_percent(self, host: HostHealth, field: str) -> float:
        metric = getattr(host, field)
        if metric.unit == "percent":
            return metric.used
        if metric.total <= 0:
            return 0
        return (metric.used / metric.total) * 100


alarm_engine = AlarmEngine()
