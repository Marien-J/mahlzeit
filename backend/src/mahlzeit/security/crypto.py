"""AES-256-GCM encryption for secrets at rest, keyed by ENCRYPTION_KEY from the environment."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mahlzeit.config import get_settings

_VERSION = b"\x01"


class EncryptionKeyMissing(RuntimeError):
    pass


def new_key() -> str:
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode().rstrip("=")


def _key(raw: str | None = None) -> bytes:
    value = raw if raw is not None else get_settings().encryption_key
    if not value:
        raise EncryptionKeyMissing("ENCRYPTION_KEY is not set")
    try:
        key = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        key = b""
    if len(key) != 32:
        raise EncryptionKeyMissing("ENCRYPTION_KEY must be 32 bytes, base64url encoded")
    return key


def encrypt(plaintext: bytes, *, aad: bytes = b"", key: str | None = None) -> bytes:
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(_key(key)).encrypt(nonce, plaintext, aad)


def decrypt(blob: bytes, *, aad: bytes = b"", key: str | None = None) -> bytes:
    if blob[:1] != _VERSION:
        raise ValueError("unknown ciphertext version")
    return AESGCM(_key(key)).decrypt(blob[1:13], blob[13:], aad)
