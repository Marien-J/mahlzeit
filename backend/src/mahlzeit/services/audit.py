"""Change records: who changed what, through which client."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from mahlzeit.domain.permissions import Actor, Client
from mahlzeit.models import ChangeRecord
from mahlzeit.services import events


def record(
    db: Session,
    *,
    actor: Actor | None,
    entity: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    household_id: uuid.UUID | None = None,
    client: Client | None = None,
) -> ChangeRecord:
    """Add a change record to the current transaction. Never put secrets in before/after."""
    resolved = client or (actor.client if actor else None)
    if resolved is None:
        raise ValueError("a change without an actor needs an explicit client")
    if household_id is None and actor is not None:
        household_id = actor.household_id
    change = ChangeRecord(
        household_id=household_id,
        user_id=actor.user_id if actor else None,
        client=resolved.value,
        entity=entity,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
    )
    db.add(change)
    if household_id is not None:
        events.publish(db, household_id, entity, change.user_id)
    return change
