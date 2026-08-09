"""
Encrypts google_refresh_token at rest with Fernet (symmetric, authenticated)
so a database leak doesn't also hand out live Google Calendar access for
every connected user. Not used for anything else — passwords are hashed
(one-way, via bcrypt in app/auth.py), not encrypted, since we never need to
recover them.
"""

from cryptography.fernet import Fernet

from app.config import settings

_fernet = Fernet(settings.token_encryption_key.encode()) if settings.token_encryption_key else None


def encrypt(value: str) -> str:
    if not _fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not _fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    return _fernet.decrypt(value.encode()).decode()
