from datetime import UTC, datetime

from ..database import get_connection
from ..models import (
    ExpectedStreamCreate,
    ExpectedStreamRecord,
    ExpectedStreamsResponse,
    ExpectedStreamUpdate,
)


def _parse_dt(value: str) -> datetime:
    text = value if value.endswith("Z") else f"{value}Z"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _row_to_model(row: object) -> ExpectedStreamRecord:
    assert isinstance(row, dict) or hasattr(row, "__getitem__")
    return ExpectedStreamRecord(
        id=row["id"],
        stream_id=row["stream_id"],
        friendly_name=row["friendly_name"],
        umd=row["umd"],
        customer_or_event=row["customer_or_event"],
        expected_protocol=row["expected_protocol"],
        expected_source_ip_or_cidr=row["expected_source_ip_or_cidr"],
        expected_min_bitrate=row["expected_min_bitrate"],
        expected_max_bitrate=row["expected_max_bitrate"],
        expected_resolution=row["expected_resolution"],
        expected_fps=row["expected_fps"],
        encryption_required=bool(row["encryption_required"]),
        auth_required=bool(row["auth_required"]),
        token_required=bool(row["token_required"]),
        auth_mode=row["auth_mode"],
        allowed_publish_cidrs=row["allowed_publish_cidrs"],
        allowed_play_cidrs=row["allowed_play_cidrs"],
        srt_encryption_required=bool(row["srt_encryption_required"]),
        priority=row["priority"],
        notes=row["notes"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


class ExpectedStreamsRepository:
    def list_streams(self) -> ExpectedStreamsResponse:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM expected_stream_configs
                ORDER BY priority ASC, stream_id ASC
                """
            ).fetchall()
        streams = [_row_to_model(row) for row in rows]
        return ExpectedStreamsResponse(total=len(streams), streams=streams)

    def create_stream(self, payload: ExpectedStreamCreate) -> ExpectedStreamRecord:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO expected_stream_configs (
                    stream_id, friendly_name, umd, customer_or_event,
                    expected_protocol, expected_source_ip_or_cidr,
                    expected_min_bitrate, expected_max_bitrate,
                    expected_resolution, expected_fps, encryption_required,
                    auth_required, token_required, auth_mode,
                    allowed_publish_cidrs, allowed_play_cidrs, srt_encryption_required,
                    priority, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.stream_id,
                    payload.friendly_name,
                    payload.umd,
                    payload.customer_or_event,
                    payload.expected_protocol,
                    payload.expected_source_ip_or_cidr,
                    payload.expected_min_bitrate,
                    payload.expected_max_bitrate,
                    payload.expected_resolution,
                    payload.expected_fps,
                    int(payload.encryption_required),
                    int(payload.auth_required),
                    int(payload.token_required),
                    payload.auth_mode,
                    payload.allowed_publish_cidrs,
                    payload.allowed_play_cidrs,
                    int(payload.srt_encryption_required),
                    payload.priority,
                    payload.notes,
                ),
            )
            row = connection.execute(
                "SELECT * FROM expected_stream_configs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _row_to_model(row)

    def get_by_stream_id(self, stream_id: str) -> ExpectedStreamRecord | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM expected_stream_configs WHERE stream_id = ?",
                (stream_id,),
            ).fetchone()
        return _row_to_model(row) if row is not None else None

    def update_by_stream_id(self, stream_id: str, payload: ExpectedStreamUpdate) -> ExpectedStreamRecord | None:
        with get_connection() as connection:
            result = connection.execute(
                """
                UPDATE expected_stream_configs
                SET
                    friendly_name = ?,
                    umd = ?,
                    customer_or_event = ?,
                    expected_protocol = ?,
                    expected_source_ip_or_cidr = ?,
                    expected_min_bitrate = ?,
                    expected_max_bitrate = ?,
                    expected_resolution = ?,
                    expected_fps = ?,
                    encryption_required = ?,
                    auth_required = ?,
                    token_required = ?,
                    auth_mode = ?,
                    allowed_publish_cidrs = ?,
                    allowed_play_cidrs = ?,
                    srt_encryption_required = ?,
                    priority = ?,
                    notes = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE stream_id = ?
                """,
                (
                    payload.friendly_name,
                    payload.umd,
                    payload.customer_or_event,
                    payload.expected_protocol,
                    payload.expected_source_ip_or_cidr,
                    payload.expected_min_bitrate,
                    payload.expected_max_bitrate,
                    payload.expected_resolution,
                    payload.expected_fps,
                    int(payload.encryption_required),
                    int(payload.auth_required),
                    int(payload.token_required),
                    payload.auth_mode,
                    payload.allowed_publish_cidrs,
                    payload.allowed_play_cidrs,
                    int(payload.srt_encryption_required),
                    payload.priority,
                    payload.notes,
                    stream_id,
                ),
            )
            if result.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM expected_stream_configs WHERE stream_id = ?",
                (stream_id,),
            ).fetchone()
        return _row_to_model(row)

    def delete_by_stream_id(self, stream_id: str) -> bool:
        with get_connection() as connection:
            result = connection.execute(
                "DELETE FROM expected_stream_configs WHERE stream_id = ?",
                (stream_id,),
            )
        return result.rowcount > 0
