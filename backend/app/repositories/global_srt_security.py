from datetime import datetime

from ..database import get_connection
from ..models import GlobalSrtSecurityConfig
from ..secrets import encrypt_secret


class GlobalSrtSecurityRepository:
    def get(self) -> GlobalSrtSecurityConfig:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT srt_encryption_required, srt_pbkeylen, srt_passphrase_enc, updated_at
                FROM global_srt_security
                WHERE singleton = 1
                """
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO global_srt_security (singleton, srt_encryption_required, srt_pbkeylen, srt_passphrase_enc)
                    VALUES (1, 1, 16, '')
                    """
                )
                row = connection.execute(
                    "SELECT srt_encryption_required, srt_pbkeylen, srt_passphrase_enc, updated_at FROM global_srt_security WHERE singleton = 1"
                ).fetchone()
        assert row is not None
        return GlobalSrtSecurityConfig(
            srt_encryption_required=bool(row["srt_encryption_required"]),
            srt_pbkeylen=int(row["srt_pbkeylen"] or 16),
            has_srt_passphrase=bool((row["srt_passphrase_enc"] or "").strip()),
            srt_passphrase=None,
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00")) if row["updated_at"] else None,
        )

    def update(self, payload: GlobalSrtSecurityConfig) -> GlobalSrtSecurityConfig:
        secret_update = None
        if payload.srt_passphrase is not None:
            secret_update = encrypt_secret(payload.srt_passphrase) if payload.srt_passphrase else ""
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE global_srt_security
                SET srt_encryption_required = ?,
                    srt_pbkeylen = ?,
                    srt_passphrase_enc = COALESCE(?, srt_passphrase_enc),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE singleton = 1
                """,
                (
                    1 if payload.srt_encryption_required else 0,
                    int(payload.srt_pbkeylen),
                    secret_update,
                ),
            )
        return self.get()

