# SRS Monitor Platform

A fully dockerized starter repository for an SRS monitoring and multiviewer platform.

## Services

- `srs`: SRS media server with RTMP, HTTP server, and HTTP API enabled.
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
`PREVIEW_SERVICE_URL` backend-to-preview internal URL
`PREVIEW_PUBLIC_BASE_URL` public preview-service base URL
`VITE_BACKEND_API_URL` frontend API base URL
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

### 4) Preview/Rewrap Logic (No Transcoding)

When preview is requested, backend resolves in this order:
1. Native WebRTC URL
2. Native HLS URL
3. Native HTTP-FLV URL
4. Preview service rewrap to HLS (`-c copy`)
5. `preview_unavailable` with reason

No transcoding, scaling, or bitrate conversion is used.

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
- Preview unavailable:
  - source codec is browser-incompatible or preview input URL/protocol cannot be derived.
