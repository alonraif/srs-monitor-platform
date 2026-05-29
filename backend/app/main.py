import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import enforce_backend_api_auth
from .database import init_db
from .config import get_settings
from .session_auth import enforce_ui_session_auth
from .routers import alarms, clients, config_srt_security, config_streams, dashboard, health, internal_srs_hooks, live, multiview, preview, stream_auth, stream_notes, streams, system
from .routers import ui_auth


settings = get_settings()

app = FastAPI(
    title="SRS Monitor Backend",
    version=settings.version,
    description="Monitoring API for SRS ingest, playback, alarms, and host health.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    try:
        enforce_backend_api_auth(request)
        enforce_ui_session_auth(request)
    except HTTPException as exc:
        headers = getattr(exc, "headers", None)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
    return await call_next(request)


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(streams.router, prefix="/api", tags=["streams"])
app.include_router(stream_notes.router, prefix="/api", tags=["stream-notes"])
app.include_router(clients.router, prefix="/api", tags=["clients"])
app.include_router(alarms.router, prefix="/api", tags=["alarms"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(config_streams.router, prefix="/api", tags=["config-streams"])
app.include_router(config_srt_security.router, prefix="/api", tags=["config-srt-security"])
app.include_router(preview.router, prefix="/api", tags=["preview"])
app.include_router(multiview.router, prefix="/api", tags=["multiview"])
app.include_router(live.router, prefix="/api", tags=["live"])
app.include_router(ui_auth.router, prefix="/api", tags=["ui-auth"])
app.include_router(stream_auth.router, prefix="/api", tags=["stream-auth"])
app.include_router(internal_srs_hooks.router, prefix="/internal", tags=["internal-srs-hooks"])
