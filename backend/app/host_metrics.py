import json
import os
import socket
import time
from datetime import UTC, datetime

import httpx
import psutil

from .config import get_settings
from .models import (
    CapacityMetric,
    HostHealth,
    NetworkInterface,
    ServiceHealth,
    ServiceState,
    SrsHealth,
    SystemResponse,
)
from .normalizer import normalize_streams
from .srs_client import fetch_srs_snapshot


PROCESS_START_TS = time.time()
DOCKER_SOCKET_PATH = "/var/run/docker.sock"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _pct_state(value: float, warn: float = 80.0, critical: float = 95.0) -> ServiceState:
    if value >= critical:
        return ServiceState.CRITICAL
    if value >= warn:
        return ServiceState.WARNING
    return ServiceState.HEALTHY


def _normalize_percent(value: float) -> float:
    # Some SRS builds expose percent-like fields as 0..1 ratios (e.g. 0.19
    # meaning 19%). Normalize to 0..100 for UI consistency.
    if 0.0 <= value <= 1.0:
        return value * 100.0
    return value


def _worst_state(states: list[ServiceState]) -> ServiceState:
    if not states:
        return ServiceState.UNKNOWN
    if ServiceState.CRITICAL in states:
        return ServiceState.CRITICAL
    if ServiceState.WARNING in states:
        return ServiceState.WARNING
    if all(state == ServiceState.UNKNOWN for state in states):
        return ServiceState.UNKNOWN
    return ServiceState.HEALTHY


class HostMetricsCollector:
    def __init__(self) -> None:
        self._last_srs_sample_time_ms: int | None = None
        self._last_srs_recv_bytes: int | None = None
        self._last_srs_send_bytes: int | None = None

    async def collect_system(self) -> SystemResponse:
        now = _now()
        snapshot = await fetch_srs_snapshot()
        host = self._collect_host_health(snapshot)
        docker_services = self._collect_docker_services(now)
        optional_services = await self._collect_optional_services(now)
        try:
            srs = self._collect_srs_health(now, docker_services, snapshot)
        except Exception as exc:
            settings = get_settings()
            srs = SrsHealth(
                api_url=settings.srs_api_url,
                status=ServiceState.UNKNOWN,
                version="unknown",
                connections=0,
                publishers=0,
                subscribers=0,
                recv_kbps=0,
                send_kbps=0,
                debug={"error": str(exc)},
            )

        services = [
            ServiceHealth(
                name="monitor-backend",
                status=host.status,
                replicas=1,
                healthy_replicas=1 if host.status in {ServiceState.HEALTHY, ServiceState.WARNING} else 0,
                latency_ms=0,
                last_check_at=now,
            ),
            *docker_services,
            *optional_services,
        ]

        return SystemResponse(generated_at=now, host=host, srs=srs, services=services)

    def _collect_host_health(self, snapshot=None) -> HostHealth:
        now = _now()
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            cpu_source = "psutil_container"
            if snapshot is not None and snapshot.reachable:
                summary = snapshot.responses.get("summaries", {})
                data = summary.get("data", {}) if isinstance(summary, dict) else {}
                system_data = data.get("system", {}) if isinstance(data, dict) else {}
                srs_cpu = system_data.get("cpu_percent")
                if isinstance(srs_cpu, (int, float)):
                    cpu = _normalize_percent(float(srs_cpu))
                    cpu_source = "srs_summary_host"
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            load = [float(value) for value in os.getloadavg()] if hasattr(os, "getloadavg") else []
            net = self._sample_network_rates()
            uptime_seconds = int(time.time() - PROCESS_START_TS)

            mem_pct = float(vm.percent)
            disk_pct = float(disk.percent)
            status = _worst_state(
                [
                    _pct_state(cpu),
                    _pct_state(mem_pct),
                    _pct_state(disk_pct),
                ]
            )

            return HostHealth(
                hostname=socket.gethostname(),
                status=status,
                uptime_seconds=uptime_seconds,
                cpu_percent=float(cpu),
                load_average=load,
                memory=CapacityMetric(used=round(mem_pct, 2), total=100.0, unit="percent"),
                disk=CapacityMetric(used=round(disk_pct, 2), total=100.0, unit="percent"),
                network=net,
                debug={
                    "backend_uptime_seconds": uptime_seconds,
                    "collected_at": now.isoformat().replace("+00:00", "Z"),
                    "cpu_source": cpu_source,
                },
            )
        except Exception as exc:
            return HostHealth(
                hostname=socket.gethostname(),
                status=ServiceState.UNKNOWN,
                uptime_seconds=int(time.time() - PROCESS_START_TS),
                cpu_percent=0.0,
                load_average=[],
                memory=CapacityMetric(used=0.0, total=100.0, unit="percent"),
                disk=CapacityMetric(used=0.0, total=100.0, unit="percent"),
                network=[],
                debug={"error": str(exc)},
            )

    def _sample_network_rates(self) -> list[NetworkInterface]:
        counters_1 = psutil.net_io_counters(pernic=True)
        t1 = time.time()
        time.sleep(0.2)
        counters_2 = psutil.net_io_counters(pernic=True)
        t2 = time.time()
        delta_seconds = max(t2 - t1, 0.001)

        interfaces: list[NetworkInterface] = []
        for name, c2 in counters_2.items():
            c1 = counters_1.get(name)
            if c1 is None:
                continue
            rx_mbps = max(((c2.bytes_recv - c1.bytes_recv) * 8 / 1_000_000) / delta_seconds, 0.0)
            tx_mbps = max(((c2.bytes_sent - c1.bytes_sent) * 8 / 1_000_000) / delta_seconds, 0.0)
            errors = max((c2.errin - c1.errin) + (c2.errout - c1.errout), 0)
            interfaces.append(
                NetworkInterface(
                    name=name,
                    rx_mbps=round(rx_mbps, 3),
                    tx_mbps=round(tx_mbps, 3),
                    errors_per_minute=int(errors * (60 / delta_seconds)),
                )
            )
        return interfaces

    def _collect_docker_services(self, now: datetime) -> list[ServiceHealth]:
        # Docker socket is optional. We only query it if mounted and reachable.
        if not os.path.exists(DOCKER_SOCKET_PATH):
            return []

        try:
            containers = self._docker_api_get("/containers/json?all=1")
        except Exception:
            return []

        if not isinstance(containers, list):
            return []

        services: list[ServiceHealth] = []
        for container in containers:
            names = container.get("Names") or []
            first_name = str(names[0]).lstrip("/") if names else str(container.get("Id", "unknown"))[:12]
            state = str(container.get("State", "unknown")).lower()
            status = ServiceState.HEALTHY if state == "running" else ServiceState.CRITICAL
            services.append(
                ServiceHealth(
                    name=f"docker:{first_name}",
                    status=status,
                    replicas=1,
                    healthy_replicas=1 if status == ServiceState.HEALTHY else 0,
                    latency_ms=0,
                    last_check_at=now,
                )
            )
        return services

    async def _collect_optional_services(self, now: datetime) -> list[ServiceHealth]:
        services: list[ServiceHealth] = []
        for name, env_key in (("cadvisor", "CADVISOR_URL"), ("node-exporter", "NODE_EXPORTER_URL")):
            url = os.getenv(env_key)
            if not url:
                continue
            status = ServiceState.UNKNOWN
            try:
                async with httpx.AsyncClient(timeout=1.5) as client:
                    response = await client.get(url)
                status = ServiceState.HEALTHY if response.status_code < 400 else ServiceState.WARNING
            except Exception:
                status = ServiceState.WARNING
            services.append(
                ServiceHealth(
                    name=name,
                    status=status,
                    replicas=1,
                    healthy_replicas=1 if status == ServiceState.HEALTHY else 0,
                    latency_ms=0,
                    last_check_at=now,
                )
            )
        return services

    def _collect_srs_health(self, now: datetime, docker_services: list[ServiceHealth], snapshot) -> SrsHealth:
        settings = get_settings()
        srs_service = next((service for service in docker_services if service.name in {"docker:srs", "docker:srs-server"}), None)
        if not snapshot.reachable:
            status = ServiceState.UNKNOWN
            if srs_service is not None and srs_service.status == ServiceState.CRITICAL:
                status = ServiceState.CRITICAL
            return SrsHealth(
                api_url=settings.srs_api_url,
                status=status,
                version="unknown",
                connections=0,
                publishers=0,
                subscribers=0,
                recv_kbps=0,
                send_kbps=0,
                debug={"srs_errors": snapshot.errors},
            )

        summary = snapshot.responses.get("summaries", {})
        data = summary.get("data", {}) if isinstance(summary, dict) else {}
        self_data = data.get("self", {}) if isinstance(data, dict) else {}
        system_data = data.get("system", {}) if isinstance(data, dict) else {}
        streams = normalize_streams(snapshot)

        connections = int(system_data.get("conn_srs", 0) or 0)
        status = ServiceState.WARNING if snapshot.errors else ServiceState.HEALTHY
        if srs_service is not None and srs_service.status == ServiceState.CRITICAL:
            status = ServiceState.CRITICAL

        recv_kbps, send_kbps = self._srs_kbps_from_counters(system_data)
        if recv_kbps == 0 and send_kbps == 0 and streams:
            recv_kbps = sum(stream.metrics.bitrate_kbps or 0 for stream in streams)
            send_kbps = sum((stream.metrics.bitrate_kbps or 0) * stream.viewers_current for stream in streams)

        return SrsHealth(
            api_url=settings.srs_api_url,
            status=status,
            version=str(self_data.get("version", "unknown")),
            connections=connections,
            publishers=sum(1 for stream in streams if str(stream.status).lower() == "online"),
            subscribers=max(connections, 0),
            recv_kbps=recv_kbps,
            send_kbps=send_kbps,
            debug={"srs_errors": snapshot.errors},
        )

    def _srs_kbps_from_counters(self, system_data: dict) -> tuple[int, int]:
        sample_time_ms = self._as_int(system_data.get("srs_sample_time"))
        recv_bytes = self._as_int(system_data.get("srs_recv_bytes"))
        send_bytes = self._as_int(system_data.get("srs_send_bytes"))
        if sample_time_ms is None or recv_bytes is None or send_bytes is None:
            return 0, 0

        prev_time = self._last_srs_sample_time_ms
        prev_recv = self._last_srs_recv_bytes
        prev_send = self._last_srs_send_bytes
        self._last_srs_sample_time_ms = sample_time_ms
        self._last_srs_recv_bytes = recv_bytes
        self._last_srs_send_bytes = send_bytes

        if prev_time is None or prev_recv is None or prev_send is None:
            return 0, 0

        dt_s = max((sample_time_ms - prev_time) / 1000.0, 0.001)
        d_recv = max(recv_bytes - prev_recv, 0)
        d_send = max(send_bytes - prev_send, 0)
        recv_kbps = int((d_recv * 8) / dt_s / 1000)
        send_kbps = int((d_send * 8) / dt_s / 1000)
        return recv_kbps, send_kbps

    def _docker_api_get(self, path: str) -> object:
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: docker\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            sock.connect(DOCKER_SOCKET_PATH)
            sock.sendall(request)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            sock.close()

        raw = b"".join(chunks)
        _, _, body = raw.partition(b"\r\n\r\n")
        if not body:
            return {}
        return json.loads(body.decode("utf-8", errors="replace"))

    def _as_int(self, value: object) -> int | None:
        try:
            return int(float(value))
        except Exception:
            return None

    def _bytes_to_kbps(self, value: object) -> int:
        try:
            return int(float(value) * 8 / 1000)
        except Exception:
            return 0


host_metrics_collector = HostMetricsCollector()
