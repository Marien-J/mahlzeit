"""One place to read the time, so tests can move it."""

from __future__ import annotations

from datetime import UTC, datetime

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(UTC)


def freeze(at: datetime | None) -> None:
    """Tests only: pin the time (None returns to the real clock)."""
    global _frozen
    _frozen = at
