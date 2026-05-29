from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..session_auth import extract_session_token, session_store, ui_auth_enabled, verify_password


class LoginRequest(BaseModel):
    password: str = Field(default="", min_length=1, max_length=200)


class LoginResponse(BaseModel):
    token: str


class SessionStatusResponse(BaseModel):
    authenticated: bool


router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    if not ui_auth_enabled():
        token = session_store.create()
        return LoginResponse(token=token)
    if not verify_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_password")
    return LoginResponse(token=session_store.create())


@router.post("/auth/logout")
async def logout(request: Request) -> dict[str, bool]:
    session_store.delete(extract_session_token(request))
    return {"ok": True}


@router.get("/auth/session", response_model=SessionStatusResponse)
async def session(request: Request) -> SessionStatusResponse:
    token = extract_session_token(request)
    return SessionStatusResponse(authenticated=session_store.touch_if_valid(token))
