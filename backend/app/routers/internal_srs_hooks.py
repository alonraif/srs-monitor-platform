from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from ..config import get_settings
from ..stream_auth import evaluate_stream_auth, hook_response


router = APIRouter()


def _require_hook_secret(secret: str | None) -> None:
    required = get_settings().srs_hook_shared_secret.strip()
    if not required:
        return
    if (secret or "").strip() != required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_hook_secret")


async def _handle_hook(request: Request, action: Literal["publish", "play"], secret: str | None) -> PlainTextResponse:
    _require_hook_secret(secret)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_hook_payload")

    decision = evaluate_stream_auth(payload, action)
    code = hook_response(decision)
    return PlainTextResponse(content=str(code), status_code=200)


@router.post("/srs/on_publish", response_class=PlainTextResponse)
async def srs_on_publish(request: Request, secret: str | None = Query(default=None)) -> PlainTextResponse:
    return await _handle_hook(request, "publish", secret)


@router.post("/srs/on_play", response_class=PlainTextResponse)
async def srs_on_play(request: Request, secret: str | None = Query(default=None)) -> PlainTextResponse:
    return await _handle_hook(request, "play", secret)
