"""Symmetric encryption for secrets kept in the database (e.g. a user's Slack webhook URL).

A webhook URL is effectively a password for posting into someone's workspace, so it is stored
encrypted and only decrypted at send time. The key lives in `NOTIFY_ENCRYPTION_KEY`; losing or
rotating it makes stored secrets unreadable, and the affected channels need reconnecting.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionNotConfigured(Exception):
    """`NOTIFY_ENCRYPTION_KEY` is missing or not a valid Fernet key."""


class UndecryptableSecret(Exception):
    """The stored value can't be decrypted with the current key (rotated, or corrupted)."""


def _fernet(key: str) -> Fernet:
    if not key:
        raise EncryptionNotConfigured("NOTIFY_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode())
    except ValueError as error:
        raise EncryptionNotConfigured("NOTIFY_ENCRYPTION_KEY is not a valid Fernet key") from error


def encrypt_secret(key: str, plaintext: str) -> str:
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt_secret(key: str, token: str) -> str:
    try:
        return _fernet(key).decrypt(token.encode()).decode()
    except InvalidToken as error:
        raise UndecryptableSecret("stored secret can't be decrypted with the current key") from error
