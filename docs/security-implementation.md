# Security Implementation

This document describes the current security implementation in the SRS Monitor Platform codebase.

## Overview

Security is implemented across three layers:

1. Network and exposure controls via deployment overlays and reverse proxy.
2. API and service authentication for backend, preview-service, and SRS API.
3. Stream-level authorization via SRS HTTP callbacks backed by Expected Streams policy.

## Deployment Overlays

The deployment model is consolidated into three overlays:

- `deploy/compose/docker-compose.single-host.yml`
- `deploy/compose/docker-compose.split-srs.yml`
- `deploy/compose/docker-compose.split-monitor.yml`

These overlays include the combined behavior previously tracked as phase 1/2/3.

## 1) Network and Exposure Controls

### Reverse Proxy

For public traffic, Nginx is the enforcement point:

- Single-host config: `deploy/nginx/single-host.conf`
- Split monitor config: `deploy/nginx/split-host-server-b.conf`
- Split SRS API wrapper: `deploy/nginx/split-host-server-a-srs-api.conf`

Proxy capabilities:

- TLS termination on `443`.
- HTTP -> HTTPS redirect.
- API rate limiting rules.
- Security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy).
- WebSocket upgrade support for frontend dev/HMR path.
- Single-host SRS API path proxy: `/srs-api/ -> srs:1985`.

### Certificate Handling

Custom proxy image:

- `deploy/nginx/proxy-image/Dockerfile`
- `deploy/nginx/proxy-image/entrypoint.sh`

Behavior:

- Uses provided certs from `deploy/nginx/certs/fullchain.pem` and `privkey.pem`.
- If missing, auto-generates self-signed certs (dev fallback).

### Port Exposure Policy

Single-host overlay:

- Public: proxy `80/443`, selected SRS media ports.
- Internal-only: backend service port, preview-service port.
- SRS API is consumed via proxy/internal paths, not intended for direct internet exposure.

Split-host overlays:

- Server A (SRS): media ports + optional SRS API proxy wrapper.
- Server B (monitor stack): public proxy, internal backend/UI/preview services.

## 2) API and Service Authentication

### Backend API Key Auth

Backend middleware enforces API auth when enabled:

- File: `backend/app/auth.py`
- Wired in: `backend/app/main.py`

Controls:

- `BACKEND_API_AUTH_ENABLED=true|false`
- `BACKEND_READ_API_KEY`
- `BACKEND_WRITE_API_KEY`

Behavior:

- `/api/health` and `/api/live` are exempt.
- `OPTIONS` is exempt for CORS preflight.
- Read methods (`GET`, `HEAD`) require read key.
- Mutating methods require write key (or read key fallback if write key is unset).
- Accepts either:
  - `Authorization: Bearer <key>`
  - `X-API-Key: <key>`

### Frontend -> Backend Auth Header

Frontend supports API key injection:

- File: `frontend/src/api.ts`
- Env: `VITE_BACKEND_API_KEY`

Behavior:

- Adds `Authorization: Bearer <VITE_BACKEND_API_KEY>` to backend API requests.

### Backend -> Preview-Service Auth

- Backend client: `backend/app/preview_client.py`
- Preview enforcement: `preview-service/app/security.py`, `preview-service/app/main.py`
- Env: `PREVIEW_AUTH_TOKEN`

Behavior:

- Backend includes bearer token when configured.
- Preview control/status endpoints require token when set.
- Preview `/health` and static preview files remain accessible.

### Backend -> SRS API Auth

- Client: `backend/app/srs_client.py`
- Env: `SRS_API_USERNAME`, `SRS_API_PASSWORD`

Behavior:

- Uses HTTP basic auth for SRS API polling when username is configured.

### SRS HTTP API Auth

Secure SRS template enables SRS API auth:

- Template: `srs/srs.secure.conf.template`
- Variables:
  - `SRS_HTTP_API_USERNAME`
  - `SRS_HTTP_API_PASSWORD`

The backend overlays align SRS API credentials with backend SRS client credentials.

## 3) Stream-Level Authorization (Expected Streams + SRS Hooks)

### Policy Model in Expected Streams

Expected stream records include stream auth policy fields:

- `auth_required`
- `token_required`
- `auth_mode` (`token_and_ip`, `ip_only`, `disabled`)
- `allowed_publish_cidrs`
- `allowed_play_cidrs`
- `srt_encryption_required`

Implementation files:

- Models: `backend/app/models.py`
- DB schema + migrations: `backend/app/database.py`
- Repository CRUD mapping: `backend/app/repositories/expected_streams.py`

### SRS Callback Endpoints

Internal callbacks exposed by backend:

- `POST /internal/srs/on_publish`
- `POST /internal/srs/on_play`

File: `backend/app/routers/internal_srs_hooks.py`

Security:

- Optional shared secret query validation via:
  - `SRS_HOOK_SHARED_SECRET`
- SRS hook URLs include `?secret=...`.

Response contract for SRS:

- Returns plain integer body as expected by SRS hooks:
  - `0` allow
  - non-zero deny (`403` used by decision engine)

### Hook Decision Engine

File: `backend/app/stream_auth.py`

Decision inputs:

- stream id from hook payload (`app` + `stream`)
- source IP
- hook query `param` parsed for token fields
- Expected Streams record policy

Decision checks:

1. Stream must exist in Expected Streams (otherwise deny).
2. Source IP must match allowed CIDR policy.
3. If token mode is active, HMAC token and expiry must validate.

Enforcement mode:

- `STREAM_AUTH_ENFORCE=false`: report-only mode (log deny reasons, allow traffic).
- `STREAM_AUTH_ENFORCE=true`: enforce deny/allow decisions.

### Signed Token Format

Token minting endpoint:

- `POST /api/stream-auth/token`
- File: `backend/app/routers/stream_auth.py`

Token config:

- `STREAM_AUTH_SECRET`
- `STREAM_AUTH_CLOCK_SKEW_SECONDS`

Signing payload:

- `action|stream_id|exp`
- HMAC-SHA256 hex digest

Accepted request params during hook verification:

- `token` (or `sig`)
- `exp` (unix epoch seconds)

## SRS Secure Template Hook Wiring

The secure template injects hook URLs:

- `__SRS_HOOK_ON_PUBLISH_URL__`
- `__SRS_HOOK_ON_PLAY_URL__`

Resolved in compose overlays through `sed` substitution at container startup.

## CORS

Backend CORS behavior:

- Exact allowlist: `CORS_ALLOW_ORIGINS`
- Optional regex: `CORS_ALLOW_ORIGIN_REGEX`
- Empty regex is treated as disabled (`None`) in app setup.

## Operational Defaults and Rollout

Recommended rollout:

1. Start with `STREAM_AUTH_ENFORCE=false` (report-only).
2. Populate/update Expected Streams auth policy.
3. Validate hook logs and token flow.
4. Enable enforcement: `STREAM_AUTH_ENFORCE=true`.

## Verification Checklist

1. Backend API auth:
- `/api/health` returns 200 without key.
- `/api/streams` returns 401 without key.
- `/api/streams` returns 200 with read key.

2. Preview-service auth:
- backend preview actions succeed with configured `PREVIEW_AUTH_TOKEN`.
- direct unauthorized preview control call is denied when token configured.

3. SRS API auth:
- `/srs-api/api/v1/summaries` requires valid SRS credentials.

4. Hook report-only mode:
- invalid token/cidr events log deny reasons but allow publish/play.

5. Hook enforce mode:
- invalid token/cidr causes hook deny and SRS rejects publish/play.

## Key Security Files

- `backend/app/auth.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/srs_client.py`
- `backend/app/preview_client.py`
- `backend/app/stream_auth.py`
- `backend/app/routers/internal_srs_hooks.py`
- `backend/app/routers/stream_auth.py`
- `backend/app/models.py`
- `backend/app/database.py`
- `backend/app/repositories/expected_streams.py`
- `preview-service/app/security.py`
- `preview-service/app/main.py`
- `srs/srs.secure.conf.template`
- `deploy/nginx/single-host.conf`
- `deploy/nginx/split-host-server-b.conf`
- `deploy/nginx/split-host-server-a-srs-api.conf`
- `deploy/nginx/proxy-image/entrypoint.sh`
- `deploy/compose/docker-compose.single-host.yml`
- `deploy/compose/docker-compose.split-srs.yml`
- `deploy/compose/docker-compose.split-monitor.yml`
