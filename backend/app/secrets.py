import base64
import hashlib

from cryptography.fernet import Fernet

from .config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().expected_stream_secret_key.strip()
    if not secret:
        raise ValueError("expected_stream_secret_key_missing")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(value: str) -> str:
    text = _fernet().decrypt(value.encode("utf-8"))
    return text.decode("utf-8")
