"""One call for 'what should we cook tonight': both people's day, tonight's plan, pending offers,
the list and what is in stock."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import MealEntry, ShoppingListItem, Store, User
from mahlzeit.services import day as day_service
from mahlzeit.services import offers, shopping, stock
from mahlzeit.services.targets import today_for

# Parts of the snapshot that later milestones fill in.
NOT_YET: tuple[str, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    today: day_service.DayResult
    tonight: list[MealEntry]
    shopping_list: list[ShoppingListItem]
    stores: list[Store]
    offers: list[offers.OfferView]
    stock: stock.Summary
    not_yet_available: tuple[str, ...] = NOT_YET


def household_snapshot(db: Session, actor: Actor, *, language: str = "de") -> Snapshot:
    today = today_for(db.get_one(User, actor.user_id))
    result = day_service.get_day(db, actor, today)
    seen: dict[object, MealEntry] = {}
    for person in result.people:
        for entry in person.entries:
            if entry.slot == Slot.DINNER:
                seen[entry.id] = entry
    return Snapshot(
        today=result,
        tonight=list(seen.values()),
        shopping_list=shopping.open_items(db, actor),
        stores=shopping.stores(db, actor),
        offers=offers.list_offers(db, actor),
        stock=stock.summary(db, actor, language=language),
    )
