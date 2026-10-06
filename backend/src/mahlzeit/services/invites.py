"""Invites: the admin invites a new household, a member invites their partner."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.domain import accounts
from mahlzeit.domain.accounts import InviteKind, InviteStatus
from mahlzeit.domain.errors import Conflict, NotFound
from mahlzeit.domain.permissions import Actor, Client, require_household
from mahlzeit.models import Household, Invite, Profile, User
from mahlzeit.security import passwords, tokens
from mahlzeit.services import audit
from mahlzeit.services.auth import StartedSession, actor_for, start_session


@dataclass(frozen=True, slots=True)
class IssuedInvite:
    """The only moment the token and code exist in clear text."""

    invite: Invite
    token: str
    code: str

    @property
    def link(self) -> str:
        return f"{get_settings().base_url.rstrip('/')}/join/{self.token}"

    @property
    def display_code(self) -> str:
        return accounts.format_invite_code(self.code)


@dataclass(frozen=True, slots=True)
class InvitePreview:
    kind: InviteKind
    status: InviteStatus
    household_name: str | None
    inviter_name: str | None
    language: str
    expires_at: datetime


def status_of(invite: Invite) -> InviteStatus:
    return accounts.invite_status(
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        now=clock.now(),
    )


def _issue(
    db: Session,
    *,
    kind: InviteKind,
    household_id: uuid.UUID | None,
    created_by: uuid.UUID | None,
    language: str,
    note: str | None,
) -> IssuedInvite:
    token = tokens.new_token()
    code = accounts.new_invite_code()
    now = clock.now()
    invite = Invite(
        kind=kind.value,
        household_id=household_id,
        created_by=created_by,
        token_hash=tokens.hash_token(token),
        code_hash=tokens.hash_token(code),
        language=language,
        note=(note or "").strip()[:120] or None,
        created_at=now,
        expires_at=now + timedelta(days=get_settings().invite_days),
    )
    db.add(invite)
    db.flush()
    return IssuedInvite(invite=invite, token=token, code=code)


def _pending_partner_invites(db: Session, household_id: uuid.UUID) -> list[Invite]:
    rows = db.scalars(
        select(Invite)
        .where(
            Invite.household_id == household_id,
            Invite.kind == InviteKind.PARTNER.value,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > clock.now(),
        )
        .order_by(Invite.created_at)
    )
    return list(rows)


def _member_count(db: Session, household_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).where(User.household_id == household_id)) or 0


def create_household_invite(
    db: Session, *, language: str = accounts.DEFAULT_LANGUAGE, note: str | None = None
) -> IssuedInvite:
    """Admin command: invite someone who will start a new household."""
    accounts.check_language(language)
    issued = _issue(
        db,
        kind=InviteKind.HOUSEHOLD,
        household_id=None,
        created_by=None,
        language=language,
        note=note,
    )
    audit.record(
        db,
        actor=None,
        client=Client.CLI,
        entity="invite",
        entity_id=issued.invite.id,
        action="created",
        after={"kind": "household"},
    )
    db.commit()
    return issued


def create_partner_invite(db: Session, actor: Actor, *, note: str | None = None) -> IssuedInvite:
    db.get_one(Household, actor.household_id, with_for_update=True)
    accounts.check_can_invite_partner(
        member_count=_member_count(db, actor.household_id),
        pending_invites=len(_pending_partner_invites(db, actor.household_id)),
    )
    inviter = db.get_one(User, actor.user_id)
    issued = _issue(
        db,
        kind=InviteKind.PARTNER,
        household_id=actor.household_id,
        created_by=actor.user_id,
        language=inviter.language,
        note=note,
    )
    audit.record(
        db,
        actor=actor,
        entity="invite",
        entity_id=issued.invite.id,
        action="created",
        after={"kind": "partner"},
    )
    db.commit()
    return issued


def list_partner_invites(db: Session, actor: Actor) -> list[Invite]:
    return _pending_partner_invites(db, actor.household_id)


def revoke_invite(db: Session, actor: Actor, invite_id: uuid.UUID) -> None:
    invite = db.get(Invite, invite_id, with_for_update=True)
    if invite is None or invite.household_id is None:
        raise NotFound()
    require_household(actor, invite.household_id)
    if status_of(invite) is not InviteStatus.PENDING:
        raise Conflict("invite_not_pending")
    invite.revoked_at = clock.now()
    audit.record(db, actor=actor, entity="invite", entity_id=invite.id, action="revoked")
    db.commit()


def _find(db: Session, key: str, *, lock: bool = False) -> Invite:
    """Find an invite by link token or by typed code."""
    key = key.strip()
    code = accounts.normalize_invite_code(key)
    if len(code) == accounts.CODE_LENGTH:
        where = Invite.code_hash == tokens.hash_token(code)
    else:
        where = Invite.token_hash == tokens.hash_token(key)
    stmt = select(Invite).where(where)
    if lock:
        stmt = stmt.with_for_update()
    invite = db.scalars(stmt).first()
    if invite is None:
        raise NotFound("invite_not_found")
    return invite


def preview(db: Session, key: str) -> InvitePreview:
    invite = _find(db, key)
    household_name = inviter_name = None
    if invite.household_id is not None:
        household_name = db.get_one(Household, invite.household_id).name
    if invite.created_by is not None:
        inviter = db.get(User, invite.created_by)
        inviter_name = inviter.display_name if inviter else None
    return InvitePreview(
        kind=InviteKind(invite.kind),
        status=status_of(invite),
        household_name=household_name,
        inviter_name=inviter_name,
        language=invite.language,
        expires_at=invite.expires_at,
    )


def accept(
    db: Session,
    *,
    key: str,
    email: str,
    password: str,
    display_name: str,
    language: str,
    time_zone: str,
    household_name: str | None = None,
    user_agent: str | None = None,
) -> StartedSession:
    """Create an account from an invite and sign it in."""
    email = accounts.clean_email(email)
    display_name = accounts.clean_display_name(display_name)
    accounts.check_password(password)
    accounts.check_language(language)
    accounts.check_time_zone(time_zone)

    invite = _find(db, key, lock=True)
    kind = InviteKind(invite.kind)
    if kind is InviteKind.PARTNER:
        assert invite.household_id is not None
        household = db.get_one(Household, invite.household_id, with_for_update=True)
        member_count = _member_count(db, household.id)
    else:
        member_count = 0
    accounts.check_invite_acceptable(status_of(invite), kind, member_count=member_count)

    if db.scalar(select(func.count()).where(User.email == email)):
        raise Conflict("email_taken")

    if kind is InviteKind.HOUSEHOLD:
        household = Household(name=accounts.clean_household_name(household_name or display_name))
        db.add(household)
        db.flush()

    user = User(
        household_id=household.id,
        email=email,
        password_hash=passwords.hash_password(password),
        display_name=display_name,
        language=language,
        time_zone=time_zone,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as err:  # a concurrent sign-up took the email
        raise Conflict("email_taken") from err
    db.add(Profile(user_id=user.id))
    now = clock.now()
    invite.accepted_at = now
    invite.accepted_by = user.id

    actor = actor_for(user)
    if kind is InviteKind.HOUSEHOLD:
        audit.record(
            db,
            actor=actor,
            entity="household",
            entity_id=household.id,
            action="created",
            after={"name": household.name},
        )
    audit.record(
        db,
        actor=actor,
        entity="user",
        entity_id=user.id,
        action="joined",
        after={"display_name": user.display_name, "invite_id": str(invite.id)},
    )
    started = start_session(db, user, user_agent=user_agent)
    db.commit()
    return started
