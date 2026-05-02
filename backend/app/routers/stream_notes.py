from fastapi import APIRouter

from ..models import StreamNotesResponse, StreamNoteUpdate
from ..repositories.operator_notes import OperatorNotesRepository


router = APIRouter()
repository = OperatorNotesRepository()


@router.get("/streams/{id}/notes", response_model=StreamNotesResponse)
async def get_stream_notes(id: str) -> StreamNotesResponse:
    return repository.get_stream_notes(id)


@router.put("/streams/{id}/notes", response_model=StreamNotesResponse)
async def update_stream_notes(id: str, payload: StreamNoteUpdate) -> StreamNotesResponse:
    return repository.add_stream_note(id, payload.note, payload.author)
