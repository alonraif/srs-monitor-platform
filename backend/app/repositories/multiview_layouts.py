import json
from datetime import UTC, datetime

from ..database import get_connection
from ..models import (
    MultiviewLayoutCreate,
    MultiviewLayoutRecord,
    MultiviewLayoutsResponse,
    MultiviewLayoutUpdate,
)


def _parse_dt(value: str) -> datetime:
    text = value if value.endswith("Z") else f"{value}Z"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _row_to_model(row: object) -> MultiviewLayoutRecord:
    assert isinstance(row, dict) or hasattr(row, "__getitem__")
    payload = json.loads(row["layout_json"])
    return MultiviewLayoutRecord(
        id=row["id"],
        name=payload.get("name", row["layout_name"]),
        type=payload.get("type", "custom"),
        is_default=bool(row["is_default"]),
        tiles=payload.get("tiles", []),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


class MultiviewLayoutsRepository:
    def list_layouts(self) -> MultiviewLayoutsResponse:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM multiview_layouts
                ORDER BY is_default DESC, layout_name ASC
                """
            ).fetchall()
        layouts = [_row_to_model(row) for row in rows]
        return MultiviewLayoutsResponse(total=len(layouts), layouts=layouts)

    def create_layout(self, payload: MultiviewLayoutCreate, created_by: str = "operator") -> MultiviewLayoutRecord:
        layout_json = json.dumps(payload.model_dump(mode="json"))
        with get_connection() as connection:
            if payload.is_default:
                connection.execute("UPDATE multiview_layouts SET is_default = 0")
            cursor = connection.execute(
                """
                INSERT INTO multiview_layouts (layout_name, layout_json, is_default, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (payload.name, layout_json, int(payload.is_default), created_by),
            )
            row = connection.execute(
                "SELECT * FROM multiview_layouts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _row_to_model(row)

    def get_layout(self, layout_id: int) -> MultiviewLayoutRecord | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM multiview_layouts WHERE id = ?",
                (layout_id,),
            ).fetchone()
        return _row_to_model(row) if row is not None else None

    def update_layout(self, layout_id: int, payload: MultiviewLayoutUpdate) -> MultiviewLayoutRecord | None:
        layout_json = json.dumps(payload.model_dump(mode="json"))
        with get_connection() as connection:
            if payload.is_default:
                connection.execute("UPDATE multiview_layouts SET is_default = 0")
            result = connection.execute(
                """
                UPDATE multiview_layouts
                SET
                    layout_name = ?,
                    layout_json = ?,
                    is_default = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (payload.name, layout_json, int(payload.is_default), layout_id),
            )
            if result.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM multiview_layouts WHERE id = ?",
                (layout_id,),
            ).fetchone()
        return _row_to_model(row)

    def delete_layout(self, layout_id: int) -> bool:
        with get_connection() as connection:
            result = connection.execute(
                "DELETE FROM multiview_layouts WHERE id = ?",
                (layout_id,),
            )
        return result.rowcount > 0

    def set_default(self, layout_id: int) -> MultiviewLayoutRecord | None:
        with get_connection() as connection:
            exists = connection.execute(
                "SELECT id FROM multiview_layouts WHERE id = ?",
                (layout_id,),
            ).fetchone()
            if exists is None:
                return None
            connection.execute("UPDATE multiview_layouts SET is_default = 0")
            connection.execute(
                """
                UPDATE multiview_layouts
                SET is_default = 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (layout_id,),
            )
            row = connection.execute(
                "SELECT * FROM multiview_layouts WHERE id = ?",
                (layout_id,),
            ).fetchone()
        return _row_to_model(row)
