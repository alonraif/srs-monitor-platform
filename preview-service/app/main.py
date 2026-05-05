import asyncio
import contextlib
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


PREVIEW_ROOT = Path("/var/preview")
ALLOWED_VIDEO_CODECS = {"h264", "avc1"}
ALLOWED_AUDIO_CODECS = {"aac", "mp3"}
ALLOWED_INPUT_SCHEMES = {"rtmp", "rtmps", "srt", "http", "https", "udp", "tcp"}
STREAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
logger = logging.getLogger("preview-service")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat().replace("+00:00", "Z") if ts else None


class StartPreviewRequest(BaseModel):
    stream_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    input_url: str = Field(min_length=1)
    input_protocol: str = Field(min_length=1, max_length=20)
    preferred_output: Literal["hls"] = "hls"
    inactivity_timeout_seconds: int = Field(default=60, ge=5, le=3600)


class StopPreviewRequest(BaseModel):
    stream_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]{1,200}$")


class PreviewStatus(BaseModel):
    stream_id: str
    state: Literal["running", "stopped", "preview_unavailable", "error"]
    input_url: str | None = None
    input_protocol: str | None = None
    preferred_output: Literal["hls"] = "hls"
    preview_url: str | None = None
    reason: str | None = None
    ffmpeg_pid: int | None = None
    started_at: str | None = None
    last_activity_at: str | None = None
    inactivity_timeout_seconds: int | None = None


class PreviewStatusResponse(BaseModel):
    generated_at: str
    previews: list[PreviewStatus]


@dataclass
class PreviewProcess:
    stream_id: str
    input_url: str
    input_protocol: str
    preview_url: str
    inactivity_timeout_seconds: int
    process: subprocess.Popen[str]
    started_at: datetime
    last_activity_at: datetime


class PreviewManager:
    def __init__(self) -> None:
        self._processes: dict[str, PreviewProcess] = {}
        self._lock = asyncio.Lock()

    async def start(self, payload: StartPreviewRequest) -> PreviewStatus:
        async with self._lock:
            safe, reason = self._validate_start_payload(payload)
            if not safe:
                return PreviewStatus(
                    stream_id=payload.stream_id,
                    state="preview_unavailable",
                    input_url=None,
                    input_protocol=payload.input_protocol,
                    reason=reason,
                )
            existing = self._processes.get(payload.stream_id)
            if existing and existing.process.poll() is None:
                self._touch_activity(existing.stream_id)
                return self._to_status(existing, "running")

            compatible, reason = await self._is_browser_compatible(payload.input_url)
            if not compatible:
                return PreviewStatus(
                    stream_id=payload.stream_id,
                    state="preview_unavailable",
                    input_url=payload.input_url,
                    input_protocol=payload.input_protocol,
                    reason=reason,
                )

            preview_dir = self._safe_preview_dir(payload.stream_id)
            if preview_dir is None:
                return PreviewStatus(
                    stream_id=payload.stream_id,
                    state="preview_unavailable",
                    input_url=None,
                    input_protocol=payload.input_protocol,
                    reason="invalid_stream_id",
                )
            self._cleanup_dir(preview_dir)
            preview_dir.mkdir(parents=True, exist_ok=True)
            output_m3u8 = preview_dir / "index.m3u8"

            ffmpeg_cmd = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-i",
                payload.input_url,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-profile:v",
                "main",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "fps=25,scale='min(1280,iw)':-2",
                "-g",
                "50",
                "-keyint_min",
                "50",
                "-sc_threshold",
                "0",
                "-b:v",
                "2500k",
                "-maxrate",
                "3000k",
                "-bufsize",
                "5000k",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-f",
                "hls",
                "-hls_time",
                "4",
                "-hls_list_size",
                "6",
                "-hls_flags",
                "delete_segments",
                str(output_m3u8),
            ]
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

            started = _now()
            preview_url = f"/preview/files/{payload.stream_id}/index.m3u8"
            process_ref = PreviewProcess(
                stream_id=payload.stream_id,
                input_url=payload.input_url,
                input_protocol=payload.input_protocol,
                preview_url=preview_url,
                inactivity_timeout_seconds=payload.inactivity_timeout_seconds,
                process=process,
                started_at=started,
                last_activity_at=started,
            )
            self._processes[payload.stream_id] = process_ref
            logger.info("started_preview stream_id=%s pid=%s", payload.stream_id, process.pid)
            return self._to_status(process_ref, "running")

    async def stop(self, stream_id: str) -> PreviewStatus:
        async with self._lock:
            proc = self._processes.pop(stream_id, None)
            if not proc:
                return PreviewStatus(stream_id=stream_id, state="stopped")

            self._terminate(proc.process)
            preview_dir = self._safe_preview_dir(stream_id)
            if preview_dir is not None:
                self._cleanup_dir(preview_dir)
            logger.info("stopped_preview stream_id=%s", stream_id)
            return PreviewStatus(stream_id=stream_id, state="stopped")

    async def status(self, stream_id: str | None = None) -> list[PreviewStatus]:
        async with self._lock:
            self._reap_dead()
            if stream_id is not None:
                proc = self._processes.get(stream_id)
                if proc:
                    self._touch_activity(stream_id)
                    return [self._to_status(proc, "running")]
                return [PreviewStatus(stream_id=stream_id, state="stopped")]

            return [self._to_status(proc, "running") for proc in self._processes.values()]

    async def watchdog(self) -> None:
        while True:
            await asyncio.sleep(2)
            async with self._lock:
                self._reap_dead()
                now = _now()
                timed_out: list[str] = []
                for stream_id, proc in self._processes.items():
                    stream_dir = self._safe_preview_dir(stream_id)
                    if stream_dir is None:
                        timed_out.append(stream_id)
                        continue
                    playlist = stream_dir / "index.m3u8"
                    if playlist.exists():
                        mtime = datetime.fromtimestamp(playlist.stat().st_mtime, tz=UTC).replace(microsecond=0)
                        proc.last_activity_at = max(proc.last_activity_at, mtime)

                    idle_seconds = (now - proc.last_activity_at).total_seconds()
                    if idle_seconds > proc.inactivity_timeout_seconds:
                        timed_out.append(stream_id)

                for stream_id in timed_out:
                    proc = self._processes.pop(stream_id, None)
                    if proc is None:
                        continue
                    self._terminate(proc.process)
                    stream_dir = self._safe_preview_dir(stream_id)
                    if stream_dir is not None:
                        self._cleanup_dir(stream_dir)
                    logger.info("timed_out_preview stream_id=%s", stream_id)

    def _touch_activity(self, stream_id: str) -> None:
        proc = self._processes.get(stream_id)
        if proc:
            proc.last_activity_at = _now()

    async def _is_browser_compatible(self, input_url: str) -> tuple[bool, str | None]:
        # Assumption: preview output is consumed by typical browser HLS players,
        # which commonly require AVC/H.264 video and AAC/MP3 audio when using
        # copy-mode remuxing (no transcoding).
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0,a:0",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "default=noprint_wrappers=1",
            input_url,
        ]
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except Exception as exc:
            return False, f"ffprobe_failed: {exc}"

        if completed.returncode != 0:
            # Assumption: if probing fails we cannot safely promise browser playback.
            return False, "input_probe_failed"

        video_codec = None
        audio_codec = None
        current_type = None
        for line in completed.stdout.splitlines():
            if line.startswith("codec_type="):
                current_type = line.split("=", 1)[1].strip()
            if line.startswith("codec_name="):
                codec = line.split("=", 1)[1].strip().lower()
                if current_type == "video" and video_codec is None:
                    video_codec = codec
                if current_type == "audio" and audio_codec is None:
                    audio_codec = codec

        if video_codec and video_codec not in ALLOWED_VIDEO_CODECS:
            return False, f"video_codec_incompatible:{video_codec}"
        if audio_codec and audio_codec not in ALLOWED_AUDIO_CODECS:
            return False, f"audio_codec_incompatible:{audio_codec}"
        return True, None

    def _to_status(self, proc: PreviewProcess, state: Literal["running", "error"]) -> PreviewStatus:
        return PreviewStatus(
            stream_id=proc.stream_id,
            state=state,
            input_url=proc.input_url,
            input_protocol=proc.input_protocol,
            preferred_output="hls",
            preview_url=proc.preview_url,
            ffmpeg_pid=proc.process.pid if proc.process.poll() is None else None,
            started_at=_iso(proc.started_at),
            last_activity_at=_iso(proc.last_activity_at),
            inactivity_timeout_seconds=proc.inactivity_timeout_seconds,
        )

    def _reap_dead(self) -> None:
        dead_streams: list[str] = []
        for stream_id, proc in self._processes.items():
            if proc.process.poll() is not None:
                dead_streams.append(stream_id)
        for stream_id in dead_streams:
            proc = self._processes.pop(stream_id, None)
            if not proc:
                continue
            stream_dir = self._safe_preview_dir(stream_id)
            if stream_dir is not None:
                self._cleanup_dir(stream_dir)
            logger.info("reaped_preview stream_id=%s exit_code=%s", stream_id, proc.process.returncode)

    def _terminate(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def _cleanup_dir(self, directory: Path) -> None:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)

    def _safe_preview_dir(self, stream_id: str) -> Path | None:
        if not STREAM_ID_PATTERN.fullmatch(stream_id):
            return None
        resolved_root = PREVIEW_ROOT.resolve()
        candidate = (PREVIEW_ROOT / stream_id).resolve()
        if resolved_root == candidate or resolved_root not in candidate.parents:
            return None
        return candidate

    def _validate_start_payload(self, payload: StartPreviewRequest) -> tuple[bool, str | None]:
        if not STREAM_ID_PATTERN.fullmatch(payload.stream_id):
            return False, "invalid_stream_id"
        parsed = urlparse(payload.input_url)
        if parsed.scheme.lower() not in ALLOWED_INPUT_SCHEMES:
            return False, "unsupported_input_scheme"
        if payload.input_protocol.lower() not in {"rtmp", "srt", "hls", "http-flv", "webrtc", "unknown", "http"}:
            return False, "unsupported_input_protocol"
        return True, None


app = FastAPI(title="SRS Preview Service")
app.mount("/preview/files", StaticFiles(directory=str(PREVIEW_ROOT), check_dir=False), name="preview-files")
manager = PreviewManager()
watchdog_task: asyncio.Task[None] | None = None


@app.on_event("startup")
async def startup() -> None:
    global watchdog_task
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    watchdog_task = asyncio.create_task(manager.watchdog())


@app.on_event("shutdown")
async def shutdown() -> None:
    global watchdog_task
    if watchdog_task:
        watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task
        watchdog_task = None
    statuses = await manager.status()
    for item in statuses:
        if item.state == "running":
            await manager.stop(item.stream_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "preview-service"}


@app.post("/preview/start", response_model=PreviewStatus)
async def preview_start(payload: StartPreviewRequest) -> PreviewStatus:
    return await manager.start(payload)


@app.post("/preview/stop", response_model=PreviewStatus)
async def preview_stop(payload: StopPreviewRequest) -> PreviewStatus:
    return await manager.stop(payload.stream_id)


@app.get("/preview/status", response_model=PreviewStatusResponse)
async def preview_status() -> PreviewStatusResponse:
    items = await manager.status()
    return PreviewStatusResponse(generated_at=_iso(_now()) or "", previews=items)


@app.get("/preview/status/{stream_id}", response_model=PreviewStatus)
async def preview_status_stream(stream_id: str) -> PreviewStatus:
    items = await manager.status(stream_id=stream_id)
    if not items:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' not found")
    return items[0]
