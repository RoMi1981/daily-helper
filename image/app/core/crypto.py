"""Password-based encryption for settings export/backup.

Format: DHBK (4 bytes magic) + salt (16 bytes) + Fernet token (variable)
Key derivation: PBKDF2HMAC-SHA256, 480 000 iterations
"""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_MAGIC = b"DHBK"
_SALT_LEN = 16
_ITERATIONS = 480_000


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_export(json_str: str, password: str) -> bytes:
    """Encrypt a JSON string with a password. Returns raw bytes."""
    salt = os.urandom(_SALT_LEN)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(json_str.encode())
    return _MAGIC + salt + token


def decrypt_export(data: bytes, password: str) -> str:
    """Decrypt bytes previously produced by encrypt_export.

    Raises ValueError on wrong magic, wrong password, or corrupted data.
    """
    if not data.startswith(_MAGIC):
        raise ValueError("Not an encrypted Daily Helper backup")
    salt = data[len(_MAGIC) : len(_MAGIC) + _SALT_LEN]
    token = data[len(_MAGIC) + _SALT_LEN :]
    key = _derive_key(password, salt)
    try:
        return Fernet(key).decrypt(token).decode()
    except InvalidToken:
        raise ValueError("Wrong password or corrupted backup file")


def is_encrypted(data: bytes) -> bool:
    """Return True if data looks like an encrypted Daily Helper backup."""
    return data.startswith(_MAGIC)
