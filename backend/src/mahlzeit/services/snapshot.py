"""One call for 'what should we cook tonight': both people's day, tonight's plan, and the rest."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import MealEntry, User
from mahlzeit.services import day as day_service
from mahlzeit.services.targets import today_for

# Parts of the snapshot that later milestones fill in.
NOT_YET = ("offers", "shopping_list", "stock")


@dataclass(frozen=True)
class Snapshot:
    today: day_service.DayResult
    tonight: list[MealEntry]
    not_yet_available: tuple[str, ...] = NOT_YET


def household_snapshot(db: Session, actor: Actor) -> Snapshot:
    today = today_for(db.get_one(User, actor.user_id))
    result = day_service.get_day(db, actor, today)
    seen: dict[object, MealEntry] = {}
    for person in result.people:
        for entry in person.entries:
            if entry.slot == Slot.DINNER:
                seen[entry.id] = entry
    return Snapshot(today=result, tonight=list(seen.values()))
