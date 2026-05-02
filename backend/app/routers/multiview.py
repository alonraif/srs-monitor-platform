import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from ..models import (
    MultiviewLayoutCreate,
    MultiviewLayoutRecord,
    MultiviewLayoutsResponse,
    MultiviewLayoutUpdate,
)
from ..repositories.multiview_layouts import MultiviewLayoutsRepository


router = APIRouter()
repository = MultiviewLayoutsRepository()


@router.get("/multiview/layouts", response_model=MultiviewLayoutsResponse)
async def list_layouts() -> MultiviewLayoutsResponse:
    return repository.list_layouts()


@router.post("/multiview/layouts", response_model=MultiviewLayoutRecord, status_code=status.HTTP_201_CREATED)
async def create_layout(payload: MultiviewLayoutCreate, request: Request) -> MultiviewLayoutRecord:
    actor = request.headers.get("x-operator", "operator")
    try:
        return repository.create_layout(payload, created_by=actor)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Layout with name '{payload.name}' already exists",
        ) from exc


@router.get("/multiview/layouts/{id}", response_model=MultiviewLayoutRecord)
async def get_layout(id: int) -> MultiviewLayoutRecord:
    layout = repository.get_layout(id)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Layout '{id}' not found")
    return layout


@router.put("/multiview/layouts/{id}", response_model=MultiviewLayoutRecord)
async def update_layout(id: int, payload: MultiviewLayoutUpdate) -> MultiviewLayoutRecord:
    try:
        layout = repository.update_layout(id, payload)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Layout with name '{payload.name}' already exists",
        ) from exc
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Layout '{id}' not found")
    return layout


@router.delete("/multiview/layouts/{id}")
async def delete_layout(id: int) -> dict[str, bool]:
    deleted = repository.delete_layout(id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Layout '{id}' not found")
    return {"deleted": True}


@router.post("/multiview/layouts/{id}/set-default", response_model=MultiviewLayoutRecord)
async def set_default_layout(id: int) -> MultiviewLayoutRecord:
    layout = repository.set_default(id)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Layout '{id}' not found")
    return layout
