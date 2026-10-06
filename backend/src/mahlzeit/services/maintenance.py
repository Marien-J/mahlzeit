"""Housekeeping: remove expired sign-in data and old finished jobs.

These are infrastructure rows, not household data, so no change records are written.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.models import AuthSession, Job, LoginAttempt, PasswordReset


def purge(db: Session) -> dict[str, int]:
    now = clock.now()
    counts = {
        "sessions": db.execute(delete(AuthSession).where(AuthSession.expires_at <= now)),
        "login_attempts": db.execute(
            delete(LoginAttempt).where(LoginAttempt.at < now - timedelta(days=1))
        ),
        "password_resets": db.execute(
            delete(PasswordReset).where(PasswordReset.expires_at < now - timedelta(days=1))
        ),
        "jobs": db.execute(
            delete(Job).where(
                Job.status.in_(("done", "failed")), Job.finished_at < now - timedelta(days=14)
            )
        ),
    }
    db.commit()
    return {name: result.rowcount for name, result in counts.items()}  # type: ignore[attr-defined]
