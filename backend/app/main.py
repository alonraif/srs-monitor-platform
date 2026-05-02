import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .config import get_settings
from .routers import alarms, clients, config_streams, dashboard, health, live, multiview, preview, stream_notes, streams, system


settings = get_settings()

app = FastAPI(
    title="SRS Monitor Backend",
    version=settings.version,
    description="Monitoring API for SRS ingest, playback, alarms, and host health.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(streams.router, prefix="/api", tags=["streams"])
app.include_router(stream_notes.router, prefix="/api", tags=["stream-notes"])
app.include_router(clients.router, prefix="/api", tags=["clients"])
app.include_router(alarms.router, prefix="/api", tags=["alarms"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(config_streams.router, prefix="/api", tags=["config-streams"])
app.include_router(preview.router, prefix="/api", tags=["preview"])
app.include_router(multiview.router, prefix="/api", tags=["multiview"])
app.include_router(live.router, prefix="/api", tags=["live"])
