from datetime import UTC, datetime

from ..database import get_connection
from ..models import StreamNoteEvent, StreamNotesResponse


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value if value.endswith("Z") else f"{value}Z"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


class OperatorNotesRepository:
    ENTITY_TYPE_STREAM = "stream"

    def get_stream_notes(self, stream_id: str, limit: int = 50) -> StreamNotesResponse:
        with get_connection() as connection:
            latest = connection.execute(
                """
                SELECT id, note, author, updated_at
                FROM operator_notes
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (self.ENTITY_TYPE_STREAM, stream_id),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT id, note, author, updated_at
                FROM operator_notes
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (self.ENTITY_TYPE_STREAM, stream_id, limit),
            ).fetchall()

        history = [
            StreamNoteEvent(
                id=row["id"],
                note=row["note"],
                author=row["author"],
                updated_at=_parse_dt(row["updated_at"]) or datetime.now(UTC),
            )
            for row in rows
        ]
        return StreamNotesResponse(
            stream_id=stream_id,
            note=latest["note"] if latest else "",
            updated_at=_parse_dt(latest["updated_at"]) if latest else None,
            history=history,
        )

    def add_stream_note(self, stream_id: str, note: str, author: str) -> StreamNotesResponse:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO operator_notes (entity_type, entity_id, note, author, updated_at)
                VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (self.ENTITY_TYPE_STREAM, stream_id, note, author),
            )
        return self.get_stream_notes(stream_id)
