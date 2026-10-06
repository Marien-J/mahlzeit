"""UUIDv7 ids, generated in the app so clients can create ids offline later."""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUID version 7 (RFC 9562). Ids from this process always
    increase: a 12-bit counter in rand_a orders ids made within the same millisecond, so
    rows created together keep the order they were made in."""
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:
            _counter += 1
            if _counter > 0xFFF:
                _last_ms += 1
                _counter = 0
        else:
            _last_ms, _counter = ms, 0
        ms, counter = _last_ms, _counter
    rand = int.from_bytes(os.urandom(8), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= counter << 64  # rand_a, 12 bits: the counter
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b, 62 bits
    return uuid.UUID(int=value)
