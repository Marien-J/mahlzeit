"""The day: meal entries for each person, totals against targets, what is left."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mahlzeit import clock
from mahlzeit.domain import day as rules
from mahlzeit.domain import recipes as recipe_rules
from mahlzeit.domain import shares as share_rules
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Forbidden, Invalid, NotFound
from mahlzeit.domain.nutrition import Nutrients, Part, Totals, intake, total
from mahlzeit.domain.permissions import Actor, require_household
from mahlzeit.domain.shares import PartShare
from mahlzeit.domain.targets import DayType, Targets, remaining
from mahlzeit.models import (
    ExactAmount,
    Household,
    MealComponent,
    MealEntry,
    MealParticipant,
    Recipe,
    User,
)
from mahlzeit.services import audit, items, stock
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
    recipe_id: uuid.UUID | None = None
    portions: float = 1.0
    cooked_grams: float | None = None  # a portion weighed after cooking, instead of `portions`
    plan: bool = False  # a plan for today or later; never logged on creation
    joint: bool = False  # for everyone else in the household too


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


@dataclass(frozen=True)
class PlanDay:
    day: date
    entries: list[MealEntry]


@dataclass(frozen=True)
class PlanResult:
    members: list[User]
    days: list[PlanDay]


# --- nutrition of stored entries --------------------------------------------------------------


def component_nutrients(c: MealComponent) -> Nutrients:
    if c.item is not None and c.amount is not None:
        return items.nutrients_of(c.item).scaled(c.amount)
    return Nutrients(
        kcal=c.quick_kcal, protein=c.quick_protein, carbs=c.quick_carbs, fat=c.quick_fat
    )


def entry_parts(entry: MealEntry) -> list[Part]:
    return [Part(key=str(c.id), nutrients=component_nutrients(c)) for c in entry.components]


def exact_fractions(entry: MealEntry, p: MealParticipant) -> dict[str, float]:
    """For each component the person weighed: the fraction of the dish's amount they ate."""
    amounts = {c.id: c.amount for c in entry.components if c.amount}
    return {
        str(x.component_id): share_rules.exact_fraction(
            component_amount=amounts[x.component_id], eaten=x.amount
        )
        for x in p.exact_amounts
        if x.component_id in amounts
    }


def participant_intake(entry: MealEntry, p: MealParticipant) -> Totals:
    return intake(entry_parts(entry), share=p.share, exact_fraction=exact_fractions(entry, p))


def participant_of(entry: MealEntry, user_id: uuid.UUID) -> MealParticipant | None:
    return next((p for p in entry.participants if p.user_id == user_id), None)


# --- reading ----------------------------------------------------------------------------------


def _entry_options() -> tuple[Any, ...]:
    return (
        selectinload(MealEntry.components).selectinload(MealComponent.item),
        selectinload(MealEntry.participants).selectinload(MealParticipant.exact_amounts),
        selectinload(MealEntry.participants).selectinload(MealParticipant.user),
    )


def _entries(db: Session, household_id: uuid.UUID, day: date) -> list[MealEntry]:
    return list(
        db.scalars(
            select(MealEntry)
            .where(MealEntry.household_id == household_id, MealEntry.day == day)
            .order_by(MealEntry.at, MealEntry.created_at, MealEntry.id)
            .options(*_entry_options())
        )
    )


def _merge(parts: list[Totals]) -> Totals:
    summed = total(p.values for p in parts)
    return Totals(summed.values, summed.incomplete.union(*(p.incomplete for p in parts)))


def _sum_targets(*parts: Totals) -> Nutrients:
    return total(p.values for p in parts).values


def _members(db: Session, actor: Actor) -> list[User]:
    household = db.get_one(Household, actor.household_id)
    return sorted(household.members, key=lambda m: (m.id != actor.user_id, m.created_at))


def person_day(db: Session, member: User, day: date, entries: list[MealEntry]) -> PersonDay:
    """One person's column: their entries and what they logged and planned in them."""
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
    return PersonDay(
        user=member,
        day_type=day_type,
        targets=targets,
        entries=mine,
        logged=logged_t,
        planned=planned_t,
        remaining=remaining(targets, logged_t.values),
        projection=remaining(targets, _sum_targets(logged_t, planned_t)),
    )


def get_day(db: Session, actor: Actor, day: date) -> DayResult:
    """Both people's columns for one day. Food and targets are always visible in a household."""
    entries = _entries(db, actor.household_id, day)
    return DayResult(day=day, people=[person_day(db, m, day, entries) for m in _members(db, actor)])


MAX_PLAN_RANGE = 31


def get_plan(db: Session, actor: Actor, start: date, days: int) -> PlanResult:
    """Every entry of the household from `start` for `days` days, grouped by day."""
    if not 1 <= days <= MAX_PLAN_RANGE:
        raise Invalid("range_invalid", max=MAX_PLAN_RANGE)
    try:
        end = start + timedelta(days=days - 1)
    except OverflowError as err:  # past the end of the calendar
        raise Invalid("range_invalid", max=MAX_PLAN_RANGE) from err
    rows = db.scalars(
        select(MealEntry)
        .where(MealEntry.household_id == actor.household_id, MealEntry.day.between(start, end))
        .order_by(MealEntry.day, MealEntry.at, MealEntry.created_at, MealEntry.id)
        .options(*_entry_options())
    )
    by_day: dict[date, list[MealEntry]] = {start + timedelta(days=i): [] for i in range(days)}
    for e in rows:
        by_day[e.day].append(e)
    return PlanResult(
        members=_members(db, actor), days=[PlanDay(d, es) for d, es in by_day.items()]
    )


def find_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> MealEntry | None:
    """An entry of the actor's household, or None when it is gone."""
    entry = db.scalars(
        select(MealEntry).where(MealEntry.id == entry_id).options(*_entry_options())
    ).first()
    if entry is not None:
        require_household(actor, entry.household_id)
    return entry


def get_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> MealEntry:
    entry = find_entry(db, actor, entry_id)
    if entry is None:
        raise NotFound("entry_not_found")
    return entry


def own_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> tuple[MealEntry, MealParticipant]:
    entry = get_entry(db, actor, entry_id)
    part = participant_of(entry, actor.user_id)
    if part is None:
        raise Forbidden("entry_not_yours")
    return entry, part


def others(db: Session, actor: Actor) -> list[User]:
    """The rest of the household: the people a meal can be shared with."""
    return [m for m in _members(db, actor) if m.id != actor.user_id]


# --- writing ----------------------------------------------------------------------------------


def _now_local(db: Session, actor: Actor) -> tuple[date, time]:
    user = db.get_one(User, actor.user_id)
    local = clock.now().astimezone(ZoneInfo(user.time_zone))
    return local.date(), local.time()


def _build_components(
    db: Session, actor: Actor, inputs: Iterable[ComponentInput], *, allow_unknown: bool = False
) -> list[MealComponent]:
    """Components from inputs. A food typed in to be logged needs its kcal; a plan, a copy and an
    edit may name a food without numbers ('Pizza'), and the day then counts it as incomplete
    until someone fills it in (logging is never blocked by missing data)."""
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
            if not name or (c.kcal is None and not allow_unknown):
                raise Invalid("quick_add_invalid")
            if c.kcal is not None and not 0 <= c.kcal <= QUICK_KCAL_MAX:
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


def _same_food(old: MealComponent, new: MealComponent) -> bool:
    return old.item_id == new.item_id and (
        new.item_id is not None or old.quick_name == new.quick_name
    )


def _sync_components(entry: MealEntry, built: list[MealComponent]) -> None:
    """Replace an entry's components, keeping the rows whose food stays (a weighed amount belongs
    to its component, so changing the time of a meal must not lose it). An unchanged component
    is matched first, so with two of one item the right one keeps its weighed amount."""
    pool = list(entry.components)
    result: list[MealComponent] = []
    matches: dict[int, MealComponent] = {}
    for i, new in enumerate(built):
        same = next((o for o in pool if _same_food(o, new) and o.amount == new.amount), None)
        if same is not None:
            matches[i] = same
            pool.remove(same)
    for i, new in enumerate(built):
        if i not in matches:
            found = next((o for o in pool if _same_food(o, new)), None)
            if found is not None:
                matches[i] = found
                pool.remove(found)
    for i, new in enumerate(built):
        match = matches.get(i)
        if match is None:
            result.append(new)
            continue
        match.amount = new.amount
        match.serving_label = new.serving_label
        match.serving_count = new.serving_count
        match.quick_name = new.quick_name
        match.quick_kcal = new.quick_kcal
        match.quick_protein = new.quick_protein
        match.quick_carbs = new.quick_carbs
        match.quick_fat = new.quick_fat
        match.position = i
        result.append(match)
    entry.components = result


def _recipe_components(
    db: Session, actor: Actor, data: EntryInput
) -> tuple[Recipe, list[ComponentInput], float]:
    assert data.recipe_id is not None
    recipe = db.scalars(
        select(Recipe).where(Recipe.id == data.recipe_id).options(selectinload(Recipe.ingredients))
    ).first()
    if recipe is None:
        raise NotFound("recipe_not_found")
    require_household(actor, recipe.household_id)
    portions = (
        recipe_rules.portions_from_cooked(
            data.cooked_grams, cooked_yield_g=recipe.cooked_yield_g, servings=recipe.servings
        )
        if data.cooked_grams is not None
        else data.portions
    )
    recipe_rules.check_portions(portions)
    factor = portions / recipe.servings
    return (
        recipe,
        [ComponentInput(item_id=i.item_id, amount=i.amount * factor) for i in recipe.ingredients],
        portions,
    )


def entry_title(entry: MealEntry, language: str) -> str:
    """The meal's name, or what is in it."""
    if entry.name:
        return entry.name
    return ", ".join(
        items.name_of(c.item, language) if c.item is not None else (c.quick_name or "")
        for c in entry.components
    )


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


def _shares_of(entry: MealEntry) -> dict[str, float]:
    return {str(p.user_id): round(p.share, 4) for p in entry.participants}


def _part_shares(entry: MealEntry) -> list[PartShare]:
    return [PartShare(p.user_id, p.share, p.state == EntryState.LOGGED) for p in entry.participants]


def apply_shares(entry: MealEntry, new: Mapping[Any, float]) -> None:
    """Set the shares a rule computed (a dict of user id to share) on the entry's parts."""
    for p in entry.participants:
        if p.user_id in new:
            p.share = new[p.user_id]


def _withdraw_offers(db: Session, actor: Actor, entry: MealEntry, user_id: uuid.UUID) -> None:
    """A person's pending offers of a meal end when it is no longer theirs to give."""
    from mahlzeit.services import offers  # offers builds on this module, so import late

    offers.withdraw_open(db, actor, entry_id=entry.id, user_id=user_id)


def log_food(db: Session, actor: Actor, data: EntryInput) -> MealEntry:
    """Add an entry for the actor. Past days and today are logged and future days are planned;
    `plan` makes it a plan for today or later. `joint` shares it with the rest of the household."""
    entry = _add_entry(db, actor, data)
    db.commit()
    return get_entry(db, actor, entry.id)


def _add_entry(
    db: Session, actor: Actor, data: EntryInput, *, allow_unknown: bool = False
) -> MealEntry:
    """log_food without the commit, so several entries can be added in one transaction."""
    today, now = _now_local(db, actor)
    if data.plan:
        rules.check_plan_date(data.day, today=today)
        state = EntryState.PLANNED.value
    else:
        rules.check_entry_date(data.day, today=today)
        state = rules.entry_state_for(data.day, today=today)
    planned = state == EntryState.PLANNED
    slot = Slot(data.slot)
    component_inputs = list(data.components)
    recipe = None
    if data.recipe_id is not None:
        recipe, from_recipe, portions = _recipe_components(db, actor, data)
        component_inputs = from_recipe + component_inputs
    name = (data.name or (recipe.name if recipe else "") or "").strip()[:120] or None
    if not component_inputs and planned and name:
        component_inputs = [ComponentInput(quick_name=name)]
    components = _build_components(
        db, actor, component_inputs, allow_unknown=allow_unknown or planned
    )
    if not components:
        raise Invalid("entry_empty")
    people = [actor.user_id]
    if data.joint:
        partners = others(db, actor)
        if not partners:
            raise Invalid("no_partner")
        people += [p.id for p in partners]
    each = share_rules.equal(len(people))
    entry = MealEntry(
        household_id=actor.household_id,
        day=data.day,
        slot=slot.value,
        at=(data.at or rules.default_time(slot, now=now)).replace(second=0, microsecond=0),
        name=name,
        eaten_out=data.eaten_out,
        recipe_id=recipe.id if recipe else None,
        recipe_portions=portions if recipe else None,
        created_by=actor.user_id,
        components=components,
        participants=[
            MealParticipant(
                user_id=user_id,
                state=state,
                share=each,
                logged_at=clock.now() if state == EntryState.LOGGED else None,
            )
            for user_id in people
        ],
    )
    db.add(entry)
    db.flush()
    stock.sync_entry(db, actor, entry.id, entry)
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="created",
        after=snapshot(entry) | {"state": state, "people": len(people)},
    )
    return entry


def plan_meal(db: Session, actor: Actor, data: EntryInput) -> MealEntry:
    """Plan a meal for today or later: from a recipe, from foods, or just a name."""
    return log_food(db, actor, replace(data, plan=True))


def update_entry(db: Session, actor: Actor, entry_id: uuid.UUID, patch: EntryPatch) -> MealEntry:
    """Change a meal. On a joint meal it changes the one dish for everyone on it."""
    entry, _ = own_entry(db, actor, entry_id)
    before = snapshot(entry)
    moved = False
    if patch.day is not None:
        today, _ = _now_local(db, actor)
        rules.check_entry_date(patch.day, today=today)
        moved = patch.day != entry.day
        entry.day = patch.day
        if patch.day > today:  # a future day only has plans
            for p in entry.participants:
                p.state, p.logged_at = EntryState.PLANNED.value, None
    if patch.slot is not None:
        moved = moved or Slot(patch.slot).value != entry.slot
        entry.slot = Slot(patch.slot).value
    if patch.at is not None:
        entry.at = patch.at.replace(second=0, microsecond=0)
    if patch.name is not None:
        entry.name = patch.name.strip()[:120] or None
    if patch.eaten_out is not None:
        entry.eaten_out = patch.eaten_out
    if patch.components is not None:
        components = _build_components(db, actor, patch.components, allow_unknown=True)
        if not components:
            raise Invalid("entry_empty")
        _sync_components(entry, components)
    entry.updated_at = clock.now()
    if moved:  # an offer is for a date and slot
        for p in entry.participants:
            _withdraw_offers(db, actor, entry, p.user_id)
    stock.sync_entry(db, actor, entry.id, entry)
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
    """Mark the actor's part of an entry eaten, planned or skipped. Eaten on a joint meal logs
    everyone's planned part (the dish is eaten once); the other changes are the actor's own."""
    entry, part = own_entry(db, actor, entry_id)
    before = part.state
    new = EntryState(state)
    if new == EntryState.LOGGED and entry.day > _now_local(db, actor)[0]:
        raise Invalid("eaten_in_future")  # a later day only holds plans
    part.state = new.value
    part.logged_at = clock.now() if new == EntryState.LOGGED else None
    also: list[str] = []
    if new == EntryState.LOGGED:
        for other in entry.participants:
            if other is not part and other.state == EntryState.PLANNED:
                other.state, other.logged_at = EntryState.LOGGED.value, clock.now()
                also.append(str(other.user_id))
                _withdraw_offers(db, actor, entry, other.user_id)
    if new != EntryState.PLANNED:
        _withdraw_offers(db, actor, entry, actor.user_id)
    stock.sync_entry(db, actor, entry.id, entry)
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="state",
        before={"state": before},
        after={"state": part.state, "also_logged": also},
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def remove_part(db: Session, actor: Actor, entry: MealEntry, part: MealParticipant) -> None:
    """Take one person off a meal (their pending offers of it end); the entry goes when nobody
    is left, and those still planned take over the dish."""
    user_id = part.user_id
    entry.participants.remove(part)
    _withdraw_offers(db, actor, entry, user_id)
    if not entry.participants:
        stock.sync_entry(db, actor, entry.id, None)
        db.delete(entry)
        return
    apply_shares(entry, share_rules.normalize(_part_shares(entry)))
    stock.sync_entry(db, actor, entry.id, entry)


def delete_entry(db: Session, actor: Actor, entry_id: uuid.UUID) -> None:
    """Remove the actor's part; the entry goes when nobody is left on it."""
    entry, part = own_entry(db, actor, entry_id)
    before = snapshot(entry)
    remove_part(db, actor, entry, part)
    audit.record(
        db, actor=actor, entity="meal_entry", entity_id=entry_id, action="deleted", before=before
    )
    db.commit()


def set_share(db: Session, actor: Actor, entry_id: uuid.UUID, share: float) -> MealEntry:
    """The actor's share of a dish. Those who have not eaten yet take the rest."""
    entry, part = own_entry(db, actor, entry_id)
    before = _shares_of(entry)
    part.share = share_rules.check(share, people=len(entry.participants))
    apply_shares(
        entry, share_rules.rebalance(_part_shares(entry), who=actor.user_id, share=part.share)
    )
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="shares",
        before=before,
        after=_shares_of(entry),
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def set_exact_amounts(
    db: Session, actor: Actor, entry_id: uuid.UUID, amounts: Mapping[uuid.UUID, float | None]
) -> MealEntry:
    """What the actor weighed out for themselves, per component (None goes back to the share).
    It replaces their share for those components."""
    entry, part = own_entry(db, actor, entry_id)
    before = {str(x.component_id): x.amount for x in part.exact_amounts}
    by_component = {c.id: c for c in entry.components}
    existing = {x.component_id: x for x in part.exact_amounts}
    for component_id, eaten in amounts.items():
        component = by_component.get(component_id)
        if component is None or not component.amount:
            raise Invalid("exact_amount_invalid", max=rules.MAX_AMOUNT)
        if eaten is None:
            if component_id in existing:
                part.exact_amounts.remove(existing[component_id])
            continue
        share_rules.exact_fraction(component_amount=component.amount, eaten=eaten)
        if component_id in existing:
            existing[component_id].amount = eaten
        else:
            part.exact_amounts.append(ExactAmount(component_id=component_id, amount=eaten))
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="exact_amounts",
        before=before,
        after={str(x.component_id): x.amount for x in part.exact_amounts},
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def move_entry(
    db: Session, actor: Actor, entry_id: uuid.UUID, *, before_id: uuid.UUID | None
) -> list[MealEntry]:
    """Drag an entry in the actor's day to stand before another (or last): its time follows."""
    entry, _ = own_entry(db, actor, entry_id)
    mine = [
        e for e in _entries(db, actor.household_id, entry.day) if participant_of(e, actor.user_id)
    ]
    changes = rules.retime([(e.id, e.at) for e in mine], entry.id, before=before_id)
    changed = [e for e in mine if e.id in changes]
    for e in changed:
        old = e.at
        e.at = changes[e.id]
        e.updated_at = clock.now()
        audit.record(
            db,
            actor=actor,
            entity="meal_entry",
            entity_id=e.id,
            action="moved",
            before={"at": old.isoformat(timespec="minutes")},
            after={"at": e.at.isoformat(timespec="minutes")},
        )
    db.commit()
    return changed


def _copy_inputs(entry: MealEntry, part: MealParticipant | None) -> list[ComponentInput]:
    """What one person ate of a meal, as foods: their share of each component, or what they
    weighed. A copy of a shared dinner is one's own portion, not the whole pot."""
    exact = exact_fractions(entry, part) if part else {}
    share = part.share if part else 1.0

    def part_of(value: float | None, fraction: float) -> float | None:
        return None if value is None else value * fraction

    inputs = []
    for c in entry.components:
        fraction = exact.get(str(c.id), share)
        if c.item_id is not None and c.amount is not None:
            inputs.append(ComponentInput(item_id=c.item_id, amount=c.amount * fraction))
        else:
            inputs.append(
                ComponentInput(
                    quick_name=c.quick_name,
                    kcal=part_of(c.quick_kcal, fraction),
                    protein=part_of(c.quick_protein, fraction),
                    carbs=part_of(c.quick_carbs, fraction),
                    fat=part_of(c.quick_fat, fraction),
                )
            )
    return inputs


def _copy_input(
    source: MealEntry,
    actor: Actor,
    *,
    day: date,
    slot: Slot | None = None,
    at: time | None = None,
) -> EntryInput:
    """The actor's own part, or for someone else's meal the part of the first person on it."""
    part = participant_of(source, actor.user_id) or next(iter(source.participants), None)
    target_slot = Slot(slot or source.slot)
    return EntryInput(
        day=day,
        slot=target_slot,
        at=at or (source.at if target_slot == source.slot else None),
        name=source.name,
        eaten_out=source.eaten_out,
        components=_copy_inputs(source, part),
    )


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
    entry = _add_entry(
        db, actor, _copy_input(source, actor, day=day, slot=slot, at=at), allow_unknown=True
    )
    db.commit()
    return get_entry(db, actor, entry.id)


def copy_day(db: Session, actor: Actor, *, source_day: date, day: date) -> list[MealEntry]:
    """Repeat all of the actor's entries from one day on another, all or nothing."""
    sources = [
        e for e in _entries(db, actor.household_id, source_day) if participant_of(e, actor.user_id)
    ]
    if not sources:
        raise Invalid("nothing_to_copy")
    created = [
        _add_entry(
            db,
            actor,
            _copy_input(e, actor, day=day, slot=Slot(e.slot), at=e.at),
            allow_unknown=True,
        )
        for e in sources
    ]
    db.commit()
    return [get_entry(db, actor, e.id) for e in created]
