"""Pure rules for accounts, households and invites."""

from __future__ import annotations

import secrets
import zoneinfo
from datetime import datetime
from enum import StrEnum
from functools import cache

from mahlzeit.domain.errors import Conflict, Invalid, RateLimited

MAX_MEMBERS = 4
PASSWORD_MIN = 10
PASSWORD_MAX = 256
LOGIN_MAX_EMAIL_FAILURES = 5
LOGIN_MAX_IP_FAILURES = 20
LOGIN_WINDOW_MINUTES = 15

# Crockford-style alphabet without 0, 1, I, L, O, U, so codes survive being read aloud.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 8


class InviteKind(StrEnum):
    HOUSEHOLD = "household"  # creates a new household on acceptance
    PARTNER = "partner"  # joins the inviter's household


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_password(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise Invalid("password_too_short", min=PASSWORD_MIN)
    if len(password) > PASSWORD_MAX:
        raise Invalid("password_too_long", max=PASSWORD_MAX)


def new_invite_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_invite_code(typed: str) -> str:
    return "".join(ch for ch in typed.upper() if ch.isalnum())


def format_invite_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def invite_status(
    *,
    expires_at: datetime,
    accepted_at: datetime | None,
    revoked_at: datetime | None,
    now: datetime,
) -> InviteStatus:
    if accepted_at is not None:
        return InviteStatus.ACCEPTED
    if revoked_at is not None:
        return InviteStatus.REVOKED
    if now >= expires_at:
        return InviteStatus.EXPIRED
    return InviteStatus.PENDING


_UNUSABLE = {
    InviteStatus.EXPIRED: "invite_expired",
    InviteStatus.ACCEPTED: "invite_used",
    InviteStatus.REVOKED: "invite_revoked",
}


def check_invite_acceptable(status: InviteStatus, kind: InviteKind, *, member_count: int) -> None:
    if status is not InviteStatus.PENDING:
        raise Conflict(_UNUSABLE[status])
    if kind is InviteKind.PARTNER and member_count >= MAX_MEMBERS:
        raise Conflict("household_full", max=MAX_MEMBERS)


def check_can_invite_partner(*, member_count: int, pending_invites: int) -> None:
    if member_count + pending_invites >= MAX_MEMBERS:
        raise Conflict("household_full", max=MAX_MEMBERS)


def check_login_allowed(*, email_failures: int, ip_failures: int) -> None:
    if email_failures >= LOGIN_MAX_EMAIL_FAILURES or ip_failures >= LOGIN_MAX_IP_FAILURES:
        raise RateLimited("too_many_attempts", minutes=LOGIN_WINDOW_MINUTES)


LANGUAGES = ("de", "en", "nl")
DEFAULT_LANGUAGE = "de"
DEFAULT_TIME_ZONE = "Europe/Berlin"


def clean_display_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 60:
        raise Invalid("display_name_invalid", max=60)
    return cleaned


def clean_household_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 80:
        raise Invalid("household_name_invalid", max=80)
    return cleaned


def check_time_zone(tz: str) -> None:
    if tz not in _time_zones():
        raise Invalid("time_zone_invalid")


def check_language(language: str) -> None:
    if language not in LANGUAGES:
        raise Invalid("language_invalid", allowed=list(LANGUAGES))


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def clean_email(email: str) -> str:
    """Normalise and sanity-check an address. Deliverability is proven by use, not by regex."""
    cleaned = normalize_email(email)
    local, _, domain = cleaned.partition("@")
    if (
        not local
        or "." not in domain
        or "@" in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or any(ch.isspace() for ch in cleaned)
        or len(cleaned) > 254
    ):
        raise Invalid("email_invalid")
    return cleaned
