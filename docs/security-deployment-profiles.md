# Security Deployment Profiles

This guide defines one shared security baseline plus two deployment profiles:

1. Single-host: SRS + monitor backend + UI + preview on one server.
2. Split-host: SRS on Server A, monitor stack on Server B.

Use this as the source of truth for production hardening.

## Scope and Objectives

- Protect control plane APIs (backend API, SRS HTTP API, preview-service API).
- Protect ingest and playback traffic.
- Support both deployment profiles with consistent controls.
- Keep operational changes minimal and repeatable.

## Shared Security Baseline (All Profiles)

### 1) Authentication and Authorization

- Require authentication for backend `/api/*`.
- Enforce role-based access for mutating endpoints:
  - `POST/PUT/DELETE /api/config/streams*`
  - `POST /api/preview/start`, `POST /api/preview/stop`
  - `POST /api/alarms/*`
  - `POST/PUT/DELETE /api/multiview/layouts*`
- Deny anonymous write actions.

### 2) Service-to-Service Authentication

- Backend -> preview-service: require internal bearer token or mTLS.
- Backend -> SRS HTTP API: enable and use `http_api.auth` credentials.
- Rotate credentials on schedule and after incidents.

### 3) Transport Security

- External traffic: HTTPS only.
- Redirect HTTP to HTTPS at reverse proxy.
- Validate upstream certificates for cross-host calls.

### 4) API Hardening

- CORS: exact allowlist of production UI origins only.
- Add rate limiting by path class:
  - strict on auth + mutating routes
  - moderate on read routes
- Apply request size and timeout limits.
- Add security headers (at proxy and/or app).

### 5) Logging and Detection

- Keep proxy access/error logs enabled.
- Keep backend auth/access logs enabled.
- Alert on:
  - repeated auth failures
  - repeated stream token validation failures
  - unusual source IPs publishing streams

### 6) Secrets and Configuration Hygiene

- Keep real secrets out of VCS and `.env.example`.
- Use environment injection, Docker secrets, or a secret manager.
- Separate dev/stage/prod credentials.

## Reverse Proxy Pattern (Recommended for Both Profiles)

The reverse proxy is the policy enforcement point.

- Public routes:
  - `/` -> `monitor-ui`
  - `/api/*` -> `monitor-backend`
  - optional `/rtc/*` -> SRS signaling endpoints if required
- Controls at proxy:
  - TLS termination
  - rate limiting
  - request/body limits
  - security headers
  - request-id + structured logging

Important: do not expose SRS API `:1985` directly to the internet.

## Profile A: Single-Host Deployment

### Network and Exposure Model

- Publicly exposed:
  - reverse proxy `443` (and optional `80` redirect)
  - only required media ports
- Private/internal only:
  - SRS API `1985`
  - backend app port
  - preview-service app port

### Required Controls

- Enable `http_api.auth` in `srs/srs.conf`.
- Set `http_api.crossdomain off` unless explicitly needed.
- Keep `SRS_API_URL` internal (for example `http://srs:1985`).
- Remove host port publish for `1985` in production compose.
- UI should call backend API, not SRS API directly.

### Recommended SRS Stream Controls

- Use `vhost.security` allow/deny rules for publish/play by CIDR.
- Use `http_hooks` token checks for `on_publish` (and optionally `on_play`).
- Enable SRT encryption:
  - `passphrase` (10-79 chars)
  - `pbkeylen` (`16`, `24`, or `32`; avoid `0`)

## Profile B: Split-Host Deployment

### Topology

- Server A: SRS only.
- Server B: reverse proxy + monitor UI + backend + preview-service.

### Firewall/Security Group Rules

Server A (SRS):

- Public only for required media traffic (example):
  - `1935/tcp` RTMP ingest (if used)
  - `10080/udp` SRT ingest (if used)
  - `8080/tcp` HLS/HTTP-FLV playback (if used)
  - `8000/udp` WebRTC media (if used)
- Restrict SRS API `1985/tcp` to Server B source IP only.
- Deny all other sources to `1985`.

Server B (monitor stack):

- Public: proxy `443` (and optional `80`).
- Keep backend and preview ports private to local network/containers.

### Cross-Host API Security

- Prefer TLS endpoint for SRS API on Server A (proxied and cert-protected).
- Backend on Server B should use authenticated SRS API endpoint.
- Keep SRS API auth enabled even with IP allowlist.

### Stream Access Security

- Enforce publish authorization via SRS `http_hooks` callbacks to Server B auth endpoint.
- Use short-lived signed token + expiry in stream params.
- Reject invalid or expired token in callback response.

## Repo-Specific Change Plan

### A) `docker-compose.yml`

Production changes:

- Remove public mapping for SRS API `1985`.
- Put public traffic through reverse proxy.
- Keep backend/preview internal and proxy-routed.

Current risk indicators include direct `ports` exposure for SRS API and backend.

### B) `srs/srs.conf`

Apply:

- `http_api.auth.enabled on`
- set username/password from secrets (or env overrides)
- `http_api.crossdomain off` in production
- optional `vhost.security` allow/deny list
- SRT `passphrase` + non-zero `pbkeylen`

### C) Backend config and env

- Add envs for backend auth mode and secrets (JWT/API key).
- Add env for internal preview-service auth token.
- Replace permissive CORS regex with explicit origin allowlist in production.
- Keep `SRS_API_URL` to private/proxied endpoint per profile.

### D) Frontend config

- Set `VITE_BACKEND_API_URL` to proxy/API URL.
- Avoid direct browser dependency on SRS API `:1985` in production.

## Acceptance Criteria

- SRS API `1985` is not publicly reachable.
- Backend mutation APIs reject unauthenticated requests.
- Cross-service calls require valid internal credentials.
- Invalid publish token is rejected by SRS callback flow.
- Split-host: `1985` accepts only Server B source IP.
- All browser traffic is HTTPS.

## Validation Checklist

1. Port scan shows only intended public ports.
2. Unauthenticated `curl` to backend write endpoints returns `401/403`.
3. Unauthenticated SRS API request fails.
4. Wrong preview-service token fails.
5. Invalid stream publish token fails.
6. CORS blocks unauthorized origin.

## Rollout Order

1. Deploy proxy + TLS + logging.
2. Remove direct exposure of control plane ports.
3. Enable API auth (backend and SRS), then service-to-service auth.
4. Enable stream token callbacks and SRT encryption.
5. Enable alerts and finalize runbook.

