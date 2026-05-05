# SRS Monitor Platform

A fully dockerized starter repository for an SRS monitoring and multiviewer platform.

## Services

- `srs`: SRS media server with RTMP, SRT, HTTP server/API, and WebRTC (RTC) enabled.
- `monitor-backend`: FastAPI backend exposing `/api/health`.
- `monitor-ui`: Vite frontend placeholder showing "SRS Monitor Platform".
- `preview-service`: FastAPI preview service exposing `/health`.
- `node-exporter`: Optional host metrics exporter.
- `cadvisor`: Optional container metrics exporter.

## Getting Started

```bash
cp .env.example .env
docker compose up --build
```

If a local port is already in use, change the matching `*_PORT` value in `.env`.

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- Preview health: http://localhost:8001/health
- SRS HTTP API: http://localhost:1985/api/v1/summaries
- SRS HTTP server: http://localhost:8080

## Environment Variables

`SRS_RTMP_PORT` RTMP ingest port (default `1935`)
`SRS_SRT_PORT` SRT ingest port (default `10080`)
`SRS_HTTP_PORT` SRS HTTP media port (default `8080`)
`SRS_API_PORT` SRS API port (default `1985`)
`SRS_API_URL` backend-to-SRS API URL (default `http://srs:1985`)
`SRS_API_TIMEOUT_SECONDS` SRS API timeout (default `2.5`)
`MOCK_MODE` `true|false` (default `true`)
`SQLITE_PATH` backend SQLite DB path (default `/data/monitor.db`)
`SRS_PUBLIC_HTTP_BASE_URL` public base for HLS/FLV URLs
`SRS_PUBLIC_WEBRTC_BASE_URL` public base for WebRTC URLs
`PREVIEW_PREFERRED_PROTOCOL` preview preference: `hls` or `webrtc` (default `hls`)
`PREVIEW_SERVICE_URL` backend-to-preview internal URL
`PREVIEW_PUBLIC_BASE_URL` public preview-service base URL
`VITE_BACKEND_API_URL` frontend API base URL
`VITE_SRS_RTMP_PORT`, `VITE_SRS_SRT_PORT` frontend-visible ingest ports
`VITE_SRS_PUBLIC_HTTP_BASE_URL`, `VITE_SRS_PUBLIC_WEBRTC_BASE_URL` frontend-visible SRS public URLs
`VITE_SRS_WEBRTC_API_BASE_URL` frontend-visible SRS RTC API base (used for `/rtc/v1/play/`)
`BACKEND_PORT`, `FRONTEND_PORT`, `PREVIEW_PORT` service ports
`NODE_EXPORTER_PORT`, `CADVISOR_PORT` optional monitoring profile ports

The backend starts in mock data mode by default:

```env
MOCK_MODE=true
```

Set `MOCK_MODE=false` to have the backend poll the SRS HTTP API at `SRS_API_URL`.
If SRS is unavailable, the API keeps returning responses and reports
`srs_unreachable` in the health/system state.

Backend API endpoints:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/streams`
- `GET /api/streams/{id}`
- `GET /api/clients`
- `GET /api/alarms`
- `POST /api/alarms/{id}/ack`
- `POST /api/alarms/{id}/unack`
- `GET /api/system`
- `GET /api/config/streams`
- `POST /api/config/streams`
- `PUT /api/config/streams/{id}`
- `DELETE /api/config/streams/{id}`
- `POST /api/preview/start`
- `POST /api/preview/stop`
- `GET /api/preview/status`
- `GET /api/preview/url/{stream_id}`
- `GET /api/multiview/layouts`
- `POST /api/multiview/layouts`
- `GET /api/multiview/layouts/{id}`
- `PUT /api/multiview/layouts/{id}`
- `DELETE /api/multiview/layouts/{id}`
- `POST /api/multiview/layouts/{id}/set-default`
- `GET /api/live` (Server-Sent Events)

Preview service endpoints:

- `GET /health`
- `POST /preview/start`
- `POST /preview/stop`
- `GET /preview/status`
- `GET /preview/status/{stream_id}`

Preview behavior:

- Uses FFmpeg remuxing with `-c copy` (no transcoding/scaling/bitrate change).
- Writes HLS output to `/var/preview/{stream_id}/index.m3u8`.
- Serves preview files at `/preview/files/{stream_id}/index.m3u8`.
- Returns `preview_unavailable` when probed codecs are browser-incompatible.
- Auto-stops idle previews after `inactivity_timeout_seconds`.
- Preview stream IDs are validated and constrained to safe filesystem paths.
- FFmpeg execution uses argument lists (no shell interpolation) and allowed input schemes only.
- Never stores or exposes passphrases/secrets.

Frontend:

- React + TypeScript + Vite
- Backend URL is configured via `VITE_BACKEND_API_URL`

SQLite persistence:

- Uses `SQLITE_PATH` (default `/data/monitor.db`).
- In Docker Compose, backend data is persisted in named volume `monitor_backend_data`.
- Stored tables include expected stream configs, alarm ack state, alarm history,
  multiviewer layouts, and operator notes.
- Alarm engine auto-resolves and clears inactive alarms from active state while
  retaining lifecycle events in `alarm_history`.

System metrics collection:

- `/api/system` uses `psutil` inside the backend container for CPU, memory,
  disk, network, and backend uptime.
- Docker container status (including SRS container status) is reported only if
  Docker socket is mounted at `/var/run/docker.sock`.
- Optional external probes can be enabled with `CADVISOR_URL` and
  `NODE_EXPORTER_URL`.
- Docker socket is not required.

To start optional monitoring exporters:

```bash
docker compose --profile monitoring up --build
```

## UI Screenshot Placeholders

- `docs/screenshots/dashboard.png` (placeholder)
- `docs/screenshots/streams.png` (placeholder)
- `docs/screenshots/alarms.png` (placeholder)
- `docs/screenshots/multiviewer.png` (placeholder)

## Test Commands

Backend unit tests:

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

## Streaming Test

Publish an RTMP stream to:

```text
rtmp://localhost:1935/live/test
```

Publish an SRT stream to:

```text
srt://localhost:10080?streamid=#!::r=live/test,m=publish
```

SRS exposes HTTP-FLV playback at:

```text
http://localhost:8080/live/test.flv
```

## Operations Guide

### 1) Publish Streams Into SRS

Use your SRS host/IP instead of `localhost` when publishing from another machine.

RTMP publish with FFmpeg:

```bash
ffmpeg -re -stream_loop -1 -i input.mp4 \
  -c copy -f flv rtmp://localhost:1935/live/main-program
```

SRT publish with FFmpeg:

```bash
ffmpeg -re -stream_loop -1 -i input.mp4 \
  -c copy -f mpegts "srt://localhost:10080?streamid=#!::r=live/main-program,m=publish"
```

OBS (RTMP) settings:
- Server: `rtmp://localhost:1935/live`
- Stream Key: `main-program`

### 2) Pull Streams From SRS

Browser HLS:

```text
http://localhost:8080/live/main-program.m3u8
```

HTTP-FLV:

```text
http://localhost:8080/live/main-program.flv
```

WebRTC (play URL form used by resolver/UI):

```text
webrtc://localhost/live/main-program
```

RTMP playback (FFplay/VLC):

```bash
ffplay rtmp://localhost:1935/live/main-program
```

SRT pull (request mode):

```bash
ffplay "srt://localhost:10080?streamid=#!::r=live/main-program,m=request"
```

### 3) Verify Ingest

- SRS stream API: `http://localhost:1985/api/v1/streams/`
- Platform streams UI: `http://localhost:3000/streams`
- Backend health: `http://localhost:8000/api/health`

### 3.1) A/B Test: SRT->RTMP vs Direct RTMP

Use this to isolate SRS `srt_to_rtmp` timestamp behavior.

Path A (SRT->RTMP remux, default vhost):
- Publish SRT with streamid host/app/stream: `#!::h=live/drone-x,m=publish`
- Playback HLS: `http://localhost:8080/live/drone-x.m3u8`

Path B (direct RTMP ingest, no SRT remux path):
- Publish RTMP: `rtmp://localhost:1935/live/drone-x?vhost=ab_rtmp_direct`
- Playback HLS: `http://localhost:8080/ab_rtmp_direct/live/drone-x.m3u8`

If warnings appear only on Path A, root cause is in the SRS SRT->RTMP path, not encoder output.

### 4) Preview/Rewrap Logic (No Transcoding)

When preview is requested, backend resolves by configured preference:
1. If `PREVIEW_PREFERRED_PROTOCOL=webrtc`: WebRTC -> HLS -> HTTP-FLV -> preview-service HLS rewrap
2. If `PREVIEW_PREFERRED_PROTOCOL=hls`: HLS -> HTTP-FLV -> WebRTC -> preview-service HLS rewrap
3. If no usable output exists: `preview_unavailable` with reason

No transcoding, scaling, or bitrate conversion is used.

### 4.1) Multiview Playback Badge

Each PiP overlay shows a playback badge:
- `WebRTC`
- `HLS`
- `FLV`

Notes:
- Badge is hidden when no stream is assigned to a tile.
- Badge reflects the backend-resolved preview source for that tile.

### 5) Expected Feeds (NOC Contract)

The **Expected Streams** page/API is the operational contract for what each feed should be.
Define expected properties and let alarm rules detect drift.

Configure:
- `stream_id`
- friendly name / UMD
- expected protocol
- expected source IP/CIDR
- bitrate min/max
- expected resolution/FPS
- encryption required policy
- priority/SLA
- notes

UI:
- `http://localhost:3000/expected-streams`

APIs:
- `GET /api/config/streams`
- `POST /api/config/streams`

## Remote Deployment: SRS on Server A, Monitoring on Server B

Use this when SRS runs on one host and the monitoring stack runs on another.

### Topology

- **Server A**: SRS container only
- **Server B**: `monitor-backend`, `monitor-ui`, `preview-service` (and optional exporters)

### 1) Deploy SRS on Server A

Expose these ports on Server A firewall/security group:
- `1935/tcp` (RTMP publish/play)
- `10080/udp` (SRT)
- `1985/tcp` (SRS HTTP API)
- `8080/tcp` (HLS/HTTP-FLV)

Pull, build, and start **SRS only** in detached mode:

```bash
docker compose pull srs
docker compose up --build -d srs
```

SRS is configured with `restart: unless-stopped`, so it will auto-start on host boot (as long as Docker itself starts on boot).

Verify:

```bash
curl -s http://<SERVER_A_IP>:1985/api/v1/summaries
curl -s http://<SERVER_A_IP>:1985/api/v1/streams/
```

### 2) Configure monitoring stack on Server B

Set these in `.env` on Server B:

```env
MOCK_MODE=false
SRS_API_URL=http://<SERVER_A_IP>:1985
SRS_PUBLIC_HTTP_BASE_URL=http://<SERVER_A_IP>:8080
SRS_PUBLIC_WEBRTC_BASE_URL=http://<SERVER_A_IP>:1985
PREVIEW_PUBLIC_BASE_URL=http://<SERVER_B_IP>:8001
VITE_BACKEND_API_URL=http://<SERVER_B_IP>:8000
```

Then run:

```bash
docker compose up --build -d
```

### 3) Connectivity checks from Server B

```bash
curl -s http://<SERVER_A_IP>:1985/api/v1/summaries
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/system
```

Expected:
- `mock_mode: false`
- health not `srs_unreachable`

### 4) Notes for preview-service in split deployment

- If browser-native playback is unavailable, backend asks preview-service to rewrap to HLS.
- Preview URLs served to users come from `PREVIEW_PUBLIC_BASE_URL`, so this must be reachable by user browsers.
- No transcoding is used (`-c copy`).

### 5) Optional: monitor-only compose (without local SRS)

If you want Server B to run only monitoring components, keep `srs` service stopped:

```bash
docker compose up --build -d monitor-backend monitor-ui preview-service
```
- `PUT /api/config/streams/{id}`
- `DELETE /api/config/streams/{id}`

Expected-feed-driven alarms include:
- `stream_offline`
- `bitrate_too_low`
- `bitrate_too_high`
- `unexpected_source_ip`
- `encryption_required_missing`
- `no_clients`
- `too_many_clients`

Security note:
- Do not store real passphrases in this platform.
- Encryption is tracked as policy/status only.

## Move From Mock Mode To Live Mode

Use this runbook when switching from synthetic demo data to real SRS telemetry.

### 1) Update `.env`

Set backend to live mode and point it to reachable services:

```env
MOCK_MODE=false
SRS_API_URL=http://srs:1985
SRS_API_TIMEOUT_SECONDS=2.5

# Public playback/preview URLs used by UI responses
SRS_PUBLIC_HTTP_BASE_URL=http://localhost:8080
SRS_PUBLIC_WEBRTC_BASE_URL=webrtc://localhost
PREVIEW_PUBLIC_BASE_URL=http://localhost:8001
PREVIEW_SERVICE_URL=http://preview-service:8001
```

If SRS is not running in the same Docker Compose network, set `SRS_API_URL` to that host/IP.

### 2) Restart Stack

```bash
docker compose up --build -d
```

### 3) Validate Live Connectivity

Backend health should show live mode:

```bash
curl -s http://localhost:8000/api/health
```

Expected:
- `"mock_mode": false`
- `health_state` should be `healthy` or `degraded` (not permanently `srs_unreachable`)

Check raw SRS API:

```bash
curl -s http://localhost:1985/api/v1/summaries
curl -s http://localhost:1985/api/v1/streams/
```

### 4) Publish a Real Test Stream

```bash
ffmpeg -re -stream_loop -1 -i input.mp4 \
  -c copy -f flv rtmp://localhost:1935/live/main-program
```

Then verify:
- UI Streams page shows live ingest: `http://localhost:3000/streams`
- Dashboard metrics update: `http://localhost:3000/`
- Multiviewer can assign/play stream: `http://localhost:3000/multiviewer`

### 5) Common Failure Modes

- `srs_unreachable` in health:
  - `SRS_API_URL` is wrong or not routable from backend container.
- Streams visible in SRS API but not playable in browser:
  - public base URLs are misconfigured (`SRS_PUBLIC_HTTP_BASE_URL`, `SRS_PUBLIC_WEBRTC_BASE_URL`).
- Multiview shows `WebRTC` badge but no video:
  - SRS RTC candidate is not browser-reachable (for example `localhost` from a remote browser).
  - Fix `rtc_server.candidate` in `srs/srs.conf` to a reachable host IP/DNS.
  - Ensure UDP `8000` is exposed and reachable (`docker-compose` maps `8000:8000/udp`).
  - Ensure `VITE_SRS_WEBRTC_API_BASE_URL` points to a browser-reachable SRS API endpoint.
- Preview unavailable:
  - source codec is browser-incompatible or preview input URL/protocol cannot be derived.

## Recent UI/Runtime Updates

- Multiview grid sizing fixes for dense layouts (`2x2`, `3x3`, `4x4`) to prevent tile overlap/cropping.
- UMD overlay typography now scales up on larger PiPs.
- UMD shading is anchored to overlay content instead of fixed top padding.
- Favicon serving fixed for Dockerized frontend (`frontend/favicon.svg` is now copied in image build).
