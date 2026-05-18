from fastapi import APIRouter

from ..models import GlobalSrtSecurityConfig, GlobalSrtSecurityUpdate
from ..repositories.global_srt_security import GlobalSrtSecurityRepository

router = APIRouter()
repository = GlobalSrtSecurityRepository()


@router.get("/config/srt-security", response_model=GlobalSrtSecurityConfig)
async def get_srt_security() -> GlobalSrtSecurityConfig:
    return repository.get()


@router.put("/config/srt-security", response_model=GlobalSrtSecurityConfig)
async def update_srt_security(payload: GlobalSrtSecurityUpdate) -> GlobalSrtSecurityConfig:
    current = repository.get()
    merged = GlobalSrtSecurityConfig(
        srt_encryption_required=payload.srt_encryption_required,
        srt_pbkeylen=payload.srt_pbkeylen,
        srt_passphrase=payload.srt_passphrase,
        has_srt_passphrase=current.has_srt_passphrase,
        updated_at=current.updated_at,
    )
    return repository.update(merged)

