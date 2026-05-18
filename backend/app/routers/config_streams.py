import sqlite3

from fastapi import APIRouter, HTTPException, status

from ..models import (
    ExpectedStreamCreate,
    ExpectedStreamRecord,
    ExpectedStreamsResponse,
    ExpectedStreamUpdate,
)
from ..repositories.expected_streams import ExpectedStreamsRepository


router = APIRouter()
repository = ExpectedStreamsRepository()


@router.get("/config/streams", response_model=ExpectedStreamsResponse)
async def list_expected_streams() -> ExpectedStreamsResponse:
    return repository.list_streams()


@router.post("/config/streams", response_model=ExpectedStreamRecord, status_code=status.HTTP_201_CREATED)
async def create_expected_stream(payload: ExpectedStreamCreate) -> ExpectedStreamRecord:
    try:
        return repository.create_stream(payload)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected stream '{payload.stream_id}' already exists",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.put("/config/streams/{id}", response_model=ExpectedStreamRecord)
async def update_expected_stream(id: str, payload: ExpectedStreamUpdate) -> ExpectedStreamRecord:
    try:
        result = repository.update_by_stream_id(id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expected stream '{id}' was not found",
        )
    return result


@router.delete("/config/streams/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expected_stream(id: str) -> None:
    if not repository.delete_by_stream_id(id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expected stream '{id}' was not found",
        )
