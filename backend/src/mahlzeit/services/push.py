"""Push subscriptions and notifications. Delivery runs in the worker."""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.domain.errors import Conflict, Invalid
from mahlzeit.domain.permissions import Actor
from mahlzeit.i18n import t
from mahlzeit.models import PushSubscription, User
from mahlzeit.push import Delivery, PushSender
from mahlzeit.security import crypto, tokens
from mahlzeit.services import audit, queue

MAX_SUBSCRIPTIONS_PER_USER = 10
_AAD = b"push_subscription"


def _check_endpoint(endpoint: str) -> None:
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or len(endpoint) > 2000:
        raise Invalid("push_endpoint_invalid")


def subscribe(
    db: Session,
    actor: Actor,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
) -> PushSubscription:
    if not get_settings().push_enabled:
        raise Conflict("push_not_configured")
    _check_endpoint(endpoint)
    blob = crypto.encrypt(
        json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}).encode(),
        aad=_AAD,
    )
    endpoint_hash = tokens.hash_token(endpoint)
    sub = db.scalars(
        select(PushSubscription).where(PushSubscription.endpoint_hash == endpoint_hash)
    ).first()
    if sub is None:
        sub = PushSubscription(
            endpoint_hash=endpoint_hash, user_id=actor.user_id, subscription_encrypted=blob
        )
        db.add(sub)
    else:
        # The device now belongs to whoever is signed in on it.
        sub.user_id = actor.user_id
        sub.subscription_encrypted = blob
    sub.user_agent = (user_agent or "")[:300] or None
    db.flush()
    _trim(db, actor.user_id)
    audit.record(db, actor=actor, entity="push_subscription", entity_id=sub.id, action="saved")
    db.commit()
    return sub


def _trim(db: Session, user_id: uuid.UUID) -> None:
    ids = db.scalars(
        select(PushSubscription.id)
        .where(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.created_at.desc())
        .offset(MAX_SUBSCRIPTIONS_PER_USER)
    ).all()
    if ids:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(ids)))


def unsubscribe(db: Session, actor: Actor, *, endpoint: str) -> None:
    sub = db.scalars(
        select(PushSubscription).where(
            PushSubscription.endpoint_hash == tokens.hash_token(endpoint),
            PushSubscription.user_id == actor.user_id,
        )
    ).first()
    if sub is None:
        return
    db.delete(sub)
    audit.record(db, actor=actor, entity="push_subscription", entity_id=sub.id, action="deleted")
    db.commit()


def count(db: Session, actor: Actor) -> int:
    return len(
        db.scalars(
            select(PushSubscription.id).where(PushSubscription.user_id == actor.user_id)
        ).all()
    )


def notify(db: Session, user_id: uuid.UUID, *, message: str, url: str = "/") -> None:
    """Queue a notification for every device of a user (inside the caller's transaction)."""
    queue.enqueue(
        db,
        "push.deliver",
        {"user_id": str(user_id), "message": message, "url": url},
        max_attempts=3,
    )


def send_test(db: Session, actor: Actor) -> None:
    if not get_settings().push_enabled:
        raise Conflict("push_not_configured")
    if count(db, actor) == 0:
        raise Conflict("push_no_subscription")
    notify(db, actor.user_id, message="test", url="/settings")
    db.commit()


def deliver(db: Session, payload: dict[str, Any], sender: PushSender) -> int:
    """Job handler: send one localised message to all of a user's devices. Returns sends."""
    user = db.get(User, uuid.UUID(payload["user_id"]))
    if user is None:
        return 0
    message = {
        "title": t(user.language, f"push.{payload['message']}.title"),
        "body": t(user.language, f"push.{payload['message']}.body"),
        "url": payload.get("url", "/"),
        "tag": payload["message"],
    }
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
    sent = 0
    for sub in subs:
        info = json.loads(crypto.decrypt(sub.subscription_encrypted, aad=_AAD))
        if sender.send(info, message) is Delivery.GONE:
            db.delete(sub)
        else:
            sub.last_success_at = clock.now()
            sent += 1
        db.commit()
    return sent
