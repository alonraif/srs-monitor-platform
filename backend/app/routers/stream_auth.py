from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..stream_auth import mint_stream_token


router = APIRouter()


class StreamTokenRequest(BaseModel):
    stream_id: str = Field(min_length=1, max_length=200)
    action: Literal["publish", "play"]
    ttl_seconds: int = Field(default=120, ge=10, le=3600)


class StreamTokenResponse(BaseModel):
    action: Literal["publish", "play"]
    stream_id: str
    exp: int
    token: str


@router.post("/stream-auth/token", response_model=StreamTokenResponse)
async def create_stream_auth_token(payload: StreamTokenRequest) -> StreamTokenResponse:
    exp = int((datetime.now(UTC) + timedelta(seconds=payload.ttl_seconds)).timestamp())
    token = mint_stream_token(payload.action, payload.stream_id, exp)
    return StreamTokenResponse(**token)
