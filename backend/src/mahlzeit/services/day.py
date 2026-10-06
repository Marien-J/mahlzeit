"""The day: meal entries for each person, totals against targets, what is left."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mahlzeit import clock
from mahlzeit.domain import day as rules
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Forbidden, Invalid, NotFound
from mahlzeit.domain.nutrition import Nutrients, Part, Totals, intake, total
from mahlzeit.domain.permissions import Actor, require_household
from mahlzeit.domain.targets import DayType, Targets, remaining
from mahlzeit.models import (
    Household,
    MealComponent,
    MealEntry,
    MealParticipant,
    Recipe,
    User,
)
from mahlzeit.services import audit, items
from mahlzeit.services.targets import targets_on

QUICK_KCAL_MAX = 10_000


@dataclass
class ComponentInput:
    """An item with an amount (or a number of servings), or a quick-add with typed-in values."""

    item_id: uuid.UUID | None = None
    amount: float | None = None
    serving_label: str | None = None
    serving_count: float | None = None
    quick_name: str | None = None
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None


@dataclass
class EntryInput:
    day: date
    slot: Slot
    at: time | None = None
    name: str | None = None
    eaten_out: bool = False
    components: list[ComponentInput] = field(default_factory=list)
    saved_meal_id: uuid.UUID | None = None
    portions: float = 1.0


@dataclass
class EntryPatch:
    day: date | None = None
    slot: Slot | None = None
    at: time | None = None
    name: str | None = None
    eaten_out: bool | None = None
    components: list[ComponentInput] | None = None


@dataclass(frozen=True)
class PersonDay:
    user: User
    day_type: DayType
    targets: Targets | None
    entries: list[MealEntry]
    logged: Totals
    planned: Totals
    remaining: Targets | None
    projection: Targets | None


@dataclass(frozen=True)
class DayResult:
    day: date
    people: list[PersonDay]


# --- nutrition of stored entries --------------------------------------------------------------


def component_nutrients(c: MealComponent) -> Nutrients:
    if c.item is not None and c.amount is not None:
        return items.nutrients_of(c.item).scaled(c.amount)
    return Nutrients(
        kcal=c.quick_kcal, protein=c.quick_protein, carbs=c.quick_carbs, fat=c.quick_fat
    )


def entry_parts(entry: MealEntry) -> list[Part]:
    return [Part(key=str(c.id), nutrients=component_nutrients(c)) for c in entry.components]


def participant_intake(entry: MealEntry, p: MealParticipant) -> Totals:
    return intake(entry_parts(entry), share=p.share)


def participant_of(entry: MealEntry, user_id: uuid.UUID) -> MealParticipant | None:
    return next((p for p in entry.participants if p.user_id == user_id), None)


# --- reading ----------------------------------------------------------------------------------


def _entries(db: Session, household_id: uuid.UUID, day: date) -> list[MealEntry]:
    return list(
        db.scalars(
            select(MealEntry)
            .where(MealEntry.household_id == household_id, MealEntry.day == day)
            .order_by(MealEntry.at, MealEntry.created_at)
            .options(
                selectinload(MealEntry.components).selectinload(MealComponent.item),
                selectinload(MealEntry.participants),
            )
        )
    )


def _merge(parts: list[Totals]) -> Totals:
    summed = total(p.values for p in parts)
    return Totals(summed.values, summed.incomplete.union(*(p.incomplete for p in parts)))


def _sum_targets(*parts: Totals) -> Nutrients:
    return total(p.values for p in parts).values


def get_day(db: Session, actor: Actor, day: date) -> DayResult:
    """Both people's columns for one day. Food and targets are always visible in a household."""
    household = db.get_one(Household, actor.household_id)
    members = sorted(household.members, key=lambda m: (m.id != actor.user_id, m.created_at))
    entries = _entries(db, actor.household_id, day)
    people = []
    for member in members:
        mine = [e for e in entries if participant_of(e, member.id)]
        logged: list[Totals] = []
        planned: list[Totals] = []
        for e in mine:
            p = participant_of(e, member.id)
            assert p is not None
            if p.state == EntryState.LOGGED:
                logged.append(participant_intake(e, p))
            elif p.state == EntryState.PLANNED:
                planned.append(participant_intake(e, p))
        logged_t, planned_t = _merge(logged), _merge(planned)
        day_type, targets = targets_on(db, member.id, day)
        people.append(
            PersonDay(
                user=member,
                day_type=day_type,
                targets=targets,
                entries=mine,
                logged=logged_t,
                planned=planned_t,
                remaining=remaining(targets, logged_t.values),
                projection=remaining(targets, _sum_targets(logged_t, planned_t)),
            )
        )
    return DayResult(day=day, people=people)


def get_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> MealEntry:
    entry = db.scalars(
        select(MealEntry)
        .where(MealEntry.id == entry_id)
        .options(
            selectinload(MealEntry.components).selectinload(MealComponent.item),
            selectinload(MealEntry.participants),
        )
    ).first()
    if entry is None:
        raise NotFound("entry_not_found")
    require_household(actor, entry.household_id)
    return entry


def _own_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> tuple[MealEntry, MealParticipant]:
    entry = get_entry(db, actor, entry_id)
    part = participant_of(entry, actor.user_id)
    if part is None:
        raise Forbidden("entry_not_yours")
    return entry, part


# --- writing ----------------------------------------------------------------------------------


def _now_local(db: Session, actor: Actor) -> tuple[date, time]:
    user = db.get_one(User, actor.user_id)
    local = clock.now().astimezone(ZoneInfo(user.time_zone))
    return local.date(), local.time()


def _build_components(
    db: Session, actor: Actor, inputs: Iterable[ComponentInput]
) -> list[MealComponent]:
    built: list[MealComponent] = []
    for i, c in enumerate(inputs):
        if c.item_id is not None:
            item = items.get(db, actor, c.item_id)
            amount = c.amount
            if amount is None and c.serving_label:
                serving = next((s for s in item.servings if s.label == c.serving_label), None)
                if serving is None:
                    raise Invalid("serving_unknown", serving=c.serving_label)
                amount = serving.amount * (c.serving_count or 1)
            if amount is None:
                raise Invalid("amount_required")
            built.append(
                MealComponent(
                    item_id=item.id,
                    item=item,
                    amount=rules.check_amount(amount),
                    serving_label=c.serving_label if c.amount is None else None,
                    serving_count=(c.serving_count or 1)
                    if c.amount is None and c.serving_label
                    else None,
                    position=i,
                )
            )
        else:
            name = (c.quick_name or "").strip()[:120]
            if not name or c.kcal is None or not 0 <= c.kcal <= QUICK_KCAL_MAX:
                raise Invalid("quick_add_invalid")
            for macro in (c.protein, c.carbs, c.fat):
                if macro is not None and not 0 <= macro <= 1_000:
                    raise Invalid("quick_add_invalid")
            built.append(
                MealComponent(
                    quick_name=name,
                    quick_kcal=c.kcal,
                    quick_protein=c.protein,
                    quick_carbs=c.carbs,
                    quick_fat=c.fat,
                    position=i,
                )
            )
    return built


def _saved_meal_components(
    db: Session, actor: Actor, recipe_id: uuid.UUID, portions: float
) -> tuple[Recipe, list[ComponentInput]]:
    recipe = db.scalars(
        select(Recipe).where(Recipe.id == recipe_id).options(selectinload(Recipe.ingredients))
    ).first()
    if recipe is None:
        raise NotFound("saved_meal_not_found")
    require_household(actor, recipe.household_id)
    if not 0 < portions <= 20:
        raise Invalid("portions_invalid")
    factor = portions / recipe.servings
    return recipe, [
        ComponentInput(item_id=i.item_id, amount=i.amount * factor) for i in recipe.ingredients
    ]


def snapshot(entry: MealEntry) -> dict[str, Any]:
    return {
        "day": entry.day.isoformat(),
        "slot": entry.slot,
        "at": entry.at.isoformat(timespec="minutes"),
        "name": entry.name,
        "eaten_out": entry.eaten_out,
        "components": [
            {
                "item_id": str(c.item_id) if c.item_id else None,
                "amount": c.amount,
                "quick_name": c.quick_name,
                "quick_kcal": c.quick_kcal,
            }
            for c in entry.components
        ],
    }


def log_food(db: Session, actor: Actor, data: EntryInput) -> MealEntry:
    """Add an entry for the actor: logged for today and the past, planned for future days."""
    today, now = _now_local(db, actor)
    rules.check_entry_date(data.day, today=today)
    slot = Slot(data.slot)
    component_inputs = list(data.components)
    recipe = None
    if data.saved_meal_id is not None:
        recipe, from_meal = _saved_meal_components(db, actor, data.saved_meal_id, data.portions)
        component_inputs = from_meal + component_inputs
    components = _build_components(db, actor, component_inputs)
    if not components:
        raise Invalid("entry_empty")
    state = rules.entry_state_for(data.day, today=today)
    entry = MealEntry(
        household_id=actor.household_id,
        day=data.day,
        slot=slot.value,
        at=data.at or rules.default_time(slot, now=now),
        name=(data.name or (recipe.name if recipe else "") or "").strip()[:120] or None,
        eaten_out=data.eaten_out,
        recipe_id=recipe.id if recipe else None,
        recipe_portions=data.portions if recipe else None,
        created_by=actor.user_id,
        components=components,
        participants=[
            MealParticipant(
                user_id=actor.user_id,
                state=state,
                share=1.0,
                logged_at=clock.now() if state == EntryState.LOGGED else None,
            )
        ],
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="created",
        after=snapshot(entry) | {"state": state},
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def update_entry(db: Session, actor: Actor, entry_id: uuid.UUID, patch: EntryPatch) -> MealEntry:
    entry, _ = _own_entry(db, actor, entry_id)
    before = snapshot(entry)
    if patch.day is not None:
        today, _ = _now_local(db, actor)
        rules.check_entry_date(patch.day, today=today)
        entry.day = patch.day
    if patch.slot is not None:
        entry.slot = Slot(patch.slot).value
    if patch.at is not None:
        entry.at = patch.at.replace(second=0, microsecond=0)
    if patch.name is not None:
        entry.name = patch.name.strip()[:120] or None
    if patch.eaten_out is not None:
        entry.eaten_out = patch.eaten_out
    if patch.components is not None:
        components = _build_components(db, actor, patch.components)
        if not components:
            raise Invalid("entry_empty")
        entry.components = components
    entry.updated_at = clock.now()
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="updated",
        before=before,
        after=snapshot(entry),
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def set_state(db: Session, actor: Actor, entry_id: uuid.UUID, state: EntryState) -> MealEntry:
    """Mark the actor's part of an entry eaten, planned or skipped."""
    entry, part = _own_entry(db, actor, entry_id)
    before = part.state
    part.state = EntryState(state).value
    part.logged_at = clock.now() if part.state == EntryState.LOGGED else None
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="state",
        before={"state": before},
        after={"state": part.state},
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def delete_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> None:
    """Remove the actor's part; the entry goes when nobody is left on it."""
    entry, part = _own_entry(db, actor, entry_id)
    before = snapshot(entry)
    entry.participants.remove(part)
    if not entry.participants:
        db.delete(entry)
    audit.record(
        db, actor=actor, entity="meal_entry", entity_id=entry_id, action="deleted", before=before
    )
    db.commit()


def _copy_inputs(entry: MealEntry) -> list[ComponentInput]:
    return [
        ComponentInput(item_id=c.item_id, amount=c.amount)
        if c.item_id is not None
        else ComponentInput(
            quick_name=c.quick_name,
            kcal=c.quick_kcal,
            protein=c.quick_protein,
            carbs=c.quick_carbs,
            fat=c.quick_fat,
        )
        for c in entry.components
    ]


def copy_entry(
    db: Session,
    actor: Actor,
    entry_id: uuid.UUID,
    *,
    day: date,
    slot: Slot | None = None,
    at: time | None = None,
) -> MealEntry:
    """Repeat an entry from the household (one's own or the partner's) for the actor."""
    source = get_entry(db, actor, entry_id)
    target_slot = Slot(slot or source.slot)
    return log_food(
        db,
        actor,
        EntryInput(
            day=day,
            slot=target_slot,
            at=at or (source.at if target_slot == source.slot else None),
            name=source.name,
            eaten_out=source.eaten_out,
            components=_copy_inputs(source),
        ),
    )


def copy_day(db: Session, actor: Actor, *, source_day: date, day: date) -> list[MealEntry]:
    """Repeat all of the actor's entries from one day on another."""
    sources = [
        e for e in _entries(db, actor.household_id, source_day) if participant_of(e, actor.user_id)
    ]
    if not sources:
        raise Invalid("nothing_to_copy")
    return [copy_entry(db, actor, e.id, day=day, slot=Slot(e.slot), at=e.at) for e in sources]
