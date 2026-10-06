"""SQLAlchemy tables. Import every model here so Alembic sees them."""

from mahlzeit.models.accounts import (
    AuthSession,
    Household,
    Invite,
    LoginAttempt,
    PasswordReset,
    Profile,
    User,
)
from mahlzeit.models.audit import ChangeRecord
from mahlzeit.models.jobs import Job
from mahlzeit.models.push import PushSubscription

__all__ = [
    "AuthSession",
    "ChangeRecord",
    "Household",
    "Invite",
    "Job",
    "LoginAttempt",
    "PasswordReset",
    "Profile",
    "PushSubscription",
    "User",
]
