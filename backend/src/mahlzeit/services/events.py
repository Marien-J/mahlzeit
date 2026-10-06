"""Tell open apps that something changed in their household.

Every change record also sends a Postgres NOTIFY on one channel. Postgres delivers it only when
the transaction commits (and folds identical ones), so a rolled-back change never reaches a
phone. Each app process listens on the channel and forwards to its event streams
(api/routes/events.py); the phones then refetch what changed.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

CHANNEL = "mahlzeit_events"


def payload(household_id: uuid.UUID, entity: str, user_id: uuid.UUID | None) -> str:
    return json.dumps(
        {
            "household": str(household_id),
            "entity": entity,
            "user": str(user_id) if user_id else None,
        }
    )


def publish(
    db: Session, household_id: uuid.UUID, entity: str, user_id: uuid.UUID | None = None
) -> None:
    db.execute(select(func.pg_notify(CHANNEL, payload(household_id, entity, user_id))))
