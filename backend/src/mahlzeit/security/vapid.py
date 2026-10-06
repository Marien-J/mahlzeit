"""VAPID key generation for web push."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def new_vapid_keys() -> tuple[str, str]:
    """Return (private, public): raw 32-byte private scalar and the uncompressed public point,
    both base64url. The public one is the browser's applicationServerKey."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(private), _b64(public)
