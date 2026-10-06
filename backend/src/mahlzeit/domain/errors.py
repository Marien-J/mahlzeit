"""Domain errors carry a stable code; adapters map the kind to a status, clients translate it."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    kind = "invalid"

    def __init__(self, code: str, **detail: Any) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class Invalid(DomainError):
    kind = "invalid"


class NotFound(DomainError):
    kind = "not_found"

    def __init__(self, code: str = "not_found", **detail: Any) -> None:
        super().__init__(code, **detail)


class Forbidden(DomainError):
    kind = "forbidden"

    def __init__(self, code: str = "forbidden", **detail: Any) -> None:
        super().__init__(code, **detail)


class Unauthorized(DomainError):
    kind = "unauthorized"

    def __init__(self, code: str = "not_authenticated", **detail: Any) -> None:
        super().__init__(code, **detail)


class Conflict(DomainError):
    kind = "conflict"


class RateLimited(DomainError):
    kind = "rate_limited"
