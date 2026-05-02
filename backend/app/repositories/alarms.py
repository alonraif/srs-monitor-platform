import json
from datetime import UTC, datetime
from typing import Any

from ..database import get_connection
from ..models import Alarm, AlarmSeverity, AlarmStatus


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value if value.endswith("Z") else f"{value}Z"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _row_to_alarm(row: Any) -> Alarm:
    return Alarm(
        id=row["alarm_id"],
        severity=AlarmSeverity(row["severity"]),
        status=AlarmStatus(row["status"]),
        stream_id=row["stream_id"],
        title=row["title"],
        description=row["description"],
        first_seen=_parse_dt(row["first_seen"]) or datetime.now(UTC),
        last_seen=_parse_dt(row["last_seen"]) or datetime.now(UTC),
        resolved_at=_parse_dt(row["resolved_at"]),
        acknowledged_by=row["acknowledged_by"],
        acknowledged_at=_parse_dt(row["acknowledged_at"]),
    )


class AlarmsRepository:
    def list_runtime(self) -> list[Alarm]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM alarm_runtime_state ORDER BY severity DESC, first_seen ASC"
            ).fetchall()
        return [_row_to_alarm(row) for row in rows]

    def get_runtime(self, alarm_id: str) -> Alarm | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM alarm_runtime_state WHERE alarm_id = ?",
                (alarm_id,),
            ).fetchone()
        return _row_to_alarm(row) if row is not None else None

    def upsert_runtime(self, alarm: Alarm) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO alarm_runtime_state (
                    alarm_id, stream_id, severity, status, title, description,
                    first_seen, last_seen, resolved_at, acknowledged_by, acknowledged_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(alarm_id) DO UPDATE SET
                    stream_id = excluded.stream_id,
                    severity = excluded.severity,
                    status = excluded.status,
                    title = excluded.title,
                    description = excluded.description,
                    first_seen = excluded.first_seen,
                    last_seen = excluded.last_seen,
                    resolved_at = excluded.resolved_at,
                    acknowledged_by = excluded.acknowledged_by,
                    acknowledged_at = excluded.acknowledged_at,
                    updated_at = excluded.updated_at
                """,
                (
                    alarm.id,
                    alarm.stream_id,
                    alarm.severity.value,
                    alarm.status.value,
                    alarm.title,
                    alarm.description,
                    alarm.first_seen.isoformat().replace("+00:00", "Z"),
                    alarm.last_seen.isoformat().replace("+00:00", "Z"),
                    alarm.resolved_at.isoformat().replace("+00:00", "Z") if alarm.resolved_at else None,
                    alarm.acknowledged_by,
                    alarm.acknowledged_at.isoformat().replace("+00:00", "Z") if alarm.acknowledged_at else None,
                ),
            )

    def delete_runtime(self, alarm_id: str) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM alarm_runtime_state WHERE alarm_id = ?", (alarm_id,))
            connection.execute("DELETE FROM alarm_ack_state WHERE alarm_id = ?", (alarm_id,))

    def set_acknowledged(self, alarm_id: str, acknowledged: bool, acknowledged_by: str, note: str = "") -> bool:
        alarm = self.get_runtime(alarm_id)
        if alarm is None:
            return False

        now = datetime.now(UTC)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO alarm_ack_state (
                    alarm_id, acknowledged, acknowledged_by, acknowledged_at, note, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
                ON CONFLICT(alarm_id) DO UPDATE SET
                    acknowledged = excluded.acknowledged,
                    acknowledged_by = excluded.acknowledged_by,
                    acknowledged_at = excluded.acknowledged_at,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    alarm_id,
                    int(acknowledged),
                    acknowledged_by if acknowledged else None,
                    now.isoformat().replace("+00:00", "Z") if acknowledged else None,
                    note,
                ),
            )
            connection.execute(
                """
                UPDATE alarm_runtime_state
                SET status = ?, acknowledged_by = ?, acknowledged_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE alarm_id = ?
                """,
                (
                    AlarmStatus.ACKNOWLEDGED.value if acknowledged else AlarmStatus.ACTIVE.value,
                    acknowledged_by if acknowledged else None,
                    now.isoformat().replace("+00:00", "Z") if acknowledged else None,
                    alarm_id,
                ),
            )
        return True

    def get_ack_state(self, alarm_id: str) -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM alarm_ack_state WHERE alarm_id = ?",
                (alarm_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "alarm_id": row["alarm_id"],
            "acknowledged": bool(row["acknowledged"]),
            "acknowledged_by": row["acknowledged_by"],
            "acknowledged_at": _parse_dt(row["acknowledged_at"]),
            "note": row["note"],
            "updated_at": _parse_dt(row["updated_at"]),
        }

    def append_history(
        self,
        alarm_id: str,
        action: str,
        severity: str,
        status: str,
        message: str,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO alarm_history (
                    alarm_id, action, severity, status, message, actor, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (alarm_id, action, severity, status, message, actor, json.dumps(metadata or {})),
            )
