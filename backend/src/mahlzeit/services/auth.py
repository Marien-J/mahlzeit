"""Sign-in, sessions and passwords."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.domain import accounts
from mahlzeit.domain.errors import Invalid, Unauthorized
from mahlzeit.domain.permissions import Actor, Client
from mahlzeit.models import AuthSession, LoginAttempt, PasswordReset, User
from mahlzeit.security import passwords, tokens
from mahlzeit.services import audit, queue

SESSION_TOUCH_INTERVAL = timedelta(hours=1)
RESET_REQUESTS_PER_HOUR = 3


@dataclass(frozen=True, slots=True)
class StartedSession:
    token: str  # goes into the cookie, never stored
    session: AuthSession
    user: User


@dataclass(frozen=True, slots=True)
class CurrentSession:
    actor: Actor
    session: AuthSession
    user: User


def actor_for(user: User, client: Client = Client.UI) -> Actor:
    return Actor(
        user_id=user.id, household_id=user.household_id, client=client, is_admin=user.is_admin
    )


def start_session(db: Session, user: User, *, user_agent: str | None = None) -> StartedSession:
    """Create a session for a user inside the current transaction (the caller commits)."""
    now = clock.now()
    token = tokens.new_token()
    session = AuthSession(
        token_hash=tokens.hash_token(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        user_agent=(user_agent or "")[:300] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=get_settings().session_days),
    )
    db.add(session)
    return StartedSession(token=token, session=session, user=user)


def login(
    db: Session, *, email: str, password: str, ip: str, user_agent: str | None = None
) -> StartedSession:
    email = accounts.normalize_email(email)
    since = clock.now() - timedelta(minutes=accounts.LOGIN_WINDOW_MINUTES)
    failures = select(func.count()).where(LoginAttempt.success.is_(False), LoginAttempt.at >= since)
    accounts.check_login_allowed(
        email_failures=db.scalar(failures.where(LoginAttempt.email == email)) or 0,
        ip_failures=db.scalar(failures.where(LoginAttempt.ip == ip)) or 0,
    )
    user = db.scalars(select(User).where(User.email == email)).first()
    ok = passwords.verify_password(user.password_hash if user else None, password)
    db.add(LoginAttempt(email=email, ip=ip, success=ok))
    if not ok or user is None:
        db.commit()
        raise Unauthorized("invalid_credentials")
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    started = start_session(db, user, user_agent=user_agent)
    db.commit()
    return started


def resolve(db: Session, token: str | None) -> CurrentSession:
    """Turn a cookie token into the acting user. Sliding expiry, touched at most hourly."""
    if not token:
        raise Unauthorized()
    now = clock.now()
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == tokens.hash_token(token))
    ).first()
    if row is None:
        raise Unauthorized()
    session, user = row
    if session.expires_at <= now:
        raise Unauthorized("session_expired")
    if now - session.last_seen_at >= SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        session.expires_at = now + timedelta(days=get_settings().session_days)
        db.commit()
    return CurrentSession(actor=actor_for(user), session=session, user=user)


def logout(db: Session, current: CurrentSession) -> None:
    db.execute(delete(AuthSession).where(AuthSession.id == current.session.id))
    db.commit()


def change_password(db: Session, current: CurrentSession, *, old: str, new: str) -> None:
    """Change the caller's password and end their other sessions."""
    user = current.user
    if not passwords.verify_password(user.password_hash, old):
        raise Invalid("current_password_wrong")
    accounts.check_password(new)
    _set_password(db, user, new, actor=current.actor, keep_session=current.session.id)
    db.commit()


def request_password_reset(db: Session, *, email: str) -> None:
    """Email a reset link if SMTP is configured and the email is known. Never reveals either."""
    settings = get_settings()
    if not settings.email_enabled:
        return
    user = db.scalars(select(User).where(User.email == accounts.normalize_email(email))).first()
    if user is None:
        return
    now = clock.now()
    recent = db.scalar(
        select(func.count()).where(
            PasswordReset.user_id == user.id, PasswordReset.created_at >= now - timedelta(hours=1)
        )
    )
    if (recent or 0) >= RESET_REQUESTS_PER_HOUR:
        return
    token = tokens.new_token()
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=tokens.hash_token(token),
            created_at=now,
            expires_at=now + timedelta(minutes=settings.reset_token_minutes),
        )
    )
    queue.enqueue(
        db,
        "email.password_reset",
        {"user_id": str(user.id), "link": f"{settings.base_url.rstrip('/')}/reset/{token}"},
        max_attempts=3,
    )
    db.commit()


def confirm_password_reset(db: Session, *, token: str, new: str) -> None:
    now = clock.now()
    reset = db.scalars(
        select(PasswordReset)
        .where(PasswordReset.token_hash == tokens.hash_token(token))
        .with_for_update()
    ).first()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise Invalid("reset_token_invalid")
    accounts.check_password(new)
    user = db.get_one(User, reset.user_id)
    reset.used_at = now
    _set_password(db, user, new, actor=actor_for(user))
    db.commit()


def admin_set_password(db: Session, *, email: str, new: str) -> User:
    """Admin command fallback when SMTP is not configured."""
    user = db.scalars(select(User).where(User.email == accounts.normalize_email(email))).first()
    if user is None:
        raise Invalid("user_not_found")
    accounts.check_password(new)
    _set_password(db, user, new, actor=actor_for(user, Client.CLI))
    db.commit()
    return user


def _set_password(
    db: Session, user: User, new: str, *, actor: Actor, keep_session: uuid.UUID | None = None
) -> None:
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = clock.now()
    ended = delete(AuthSession).where(AuthSession.user_id == user.id)
    if keep_session is not None:
        ended = ended.where(AuthSession.id != keep_session)
    db.execute(ended)
    audit.record(db, actor=actor, entity="user", entity_id=user.id, action="password_changed")
