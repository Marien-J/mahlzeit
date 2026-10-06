"""The caller's household and its members."""

from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from mahlzeit.domain import accounts
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import Household
from mahlzeit.services import audit


def get(db: Session, actor: Actor) -> Household:
    return db.get_one(Household, actor.household_id, options=[selectinload(Household.members)])


def rename(db: Session, actor: Actor, name: str) -> Household:
    household = db.get_one(Household, actor.household_id)
    before = household.name
    household.name = accounts.clean_household_name(name)
    audit.record(
        db,
        actor=actor,
        entity="household",
        entity_id=household.id,
        action="renamed",
        before={"name": before},
        after={"name": household.name},
    )
    db.commit()
    return get(db, actor)
