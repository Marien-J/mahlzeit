"""Argon2id password hashing."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2-cffi defaults are Argon2id with RFC 9106 low-memory parameters

# Verified against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("mahlzeit-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Check a password. Pass None for an unknown user to spend the same time and fail."""
    try:
        matched = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return matched and password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
