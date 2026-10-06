"""Personal connector URLs for the Claude connector (M1, step 1 of connector auth).

Each person has at most one active URL. It contains a long random token that is shown once,
stored only as a hash, never logged, and can be rotated or revoked at any time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.domain.errors import Unauthorized
from mahlzeit.domain.permissions import Actor, Client
from mahlzeit.models import ConnectorToken, User
from mahlzeit.security import tokens
from mahlzeit.services import audit
from mahlzeit.services.auth import actor_for

TOUCH_INTERVAL = timedelta(minutes=10)
PATH_PREFIX = "/mcp/"


@dataclass(frozen=True)
class Issued:
    token: str

    @property
    def url(self) -> str:
        return f"{get_settings().base_url.rstrip('/')}{PATH_PREFIX}{self.token}"


def active(db: Session, actor: Actor) -> ConnectorToken | None:
    return db.scalars(
        select(ConnectorToken).where(
            ConnectorToken.user_id == actor.user_id, ConnectorToken.revoked_at.is_(None)
        )
    ).first()


def _revoke_all(db: Session, actor: Actor) -> None:
    db.execute(
        update(ConnectorToken)
        .where(ConnectorToken.user_id == actor.user_id, ConnectorToken.revoked_at.is_(None))
        .values(revoked_at=clock.now())
    )


def create(db: Session, actor: Actor) -> Issued:
    """A new personal URL. Any previous one stops working at once."""
    _revoke_all(db, actor)
    token = tokens.new_token() + tokens.new_token()  # 512 bits; it is the only credential
    row = ConnectorToken(user_id=actor.user_id, token_hash=tokens.hash_token(token))
    db.add(row)
    db.flush()
    audit.record(db, actor=actor, entity="connector_token", entity_id=row.id, action="created")
    db.commit()
    return Issued(token=token)


def revoke(db: Session, actor: Actor) -> None:
    current = active(db, actor)
    if current is None:
        return
    _revoke_all(db, actor)
    audit.record(db, actor=actor, entity="connector_token", entity_id=current.id, action="revoked")
    db.commit()


def resolve(db: Session, token: str) -> Actor:
    """The person behind a connector URL, acting through the connector client."""
    if not token or len(token) > 200:
        raise Unauthorized()
    row = db.scalars(
        select(ConnectorToken).where(
            ConnectorToken.token_hash == tokens.hash_token(token),
            ConnectorToken.revoked_at.is_(None),
        )
    ).first()
    if row is None:
        raise Unauthorized()
    now = clock.now()
    if row.last_used_at is None or now - row.last_used_at >= TOUCH_INTERVAL:
        row.last_used_at = now
        db.commit()
    return actor_for(db.get_one(User, row.user_id), Client.CONNECTOR)
