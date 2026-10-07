"""Stock: purchases put food in, eaten meals take it out, the pantry check and waste fix it.

Every change of a counted item is a movement in the ledger and the level is their sum
(domain.stock). Status-only items such as oil and spices keep no amount: buying one sets it to
ok, and a tap moves it to low or out. Stock is advisory and never blocks logging.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from mahlzeit import clock
from mahlzeit.domain import recipes as recipe_rules
from mahlzeit.domain import shopping as list_rules
from mahlzeit.domain import stock as rules
from mahlzeit.domain.catalogue import Category, TrackingMode
from mahlzeit.domain.day import EntryState
from mahlzeit.domain.errors import Invalid, NotFound
from mahlzeit.domain.permissions import Actor
from mahlzeit.domain.stock import Reason, Source, Status
from mahlzeit.models import (
    Item,
    MealComponent,
    MealEntry,
    PantryCheck,
    Profile,
    Purchase,
    PurchaseLine,
    ShoppingListItem,
    StockMovement,
    StockStatus,
    User,
)
from mahlzeit.services import audit, items, shopping
from mahlzeit.services.targets import today_for

MAX_LINES = 200
MAX_PRICE_CENTS = 1_000_000
MAX_CHECK_ITEMS = 500
MAX_REPORT_DAYS = 366
RECENT_DAYS = 90  # a counted item at zero stays on the stock page this long
_EPSILON = 1e-6


@dataclass
class LineInput:
    """A catalogue item or free text. Without an amount, the quantity is read as one."""

    item_id: uuid.UUID | None = None
    text: str | None = None
    quantity: str | None = None
    amount: float | None = None
    price_cents: int | None = None
    list_item_id: uuid.UUID | None = None


@dataclass
class PurchaseInput:
    id: uuid.UUID
    lines: list[LineInput] = field(default_factory=list)
    store_id: uuid.UUID | None = None
    day: date | None = None


@dataclass(frozen=True)
class StockRow:
    item: Item
    name: str
    mode: TrackingMode
    level: float | None  # counted items only, never below zero
    status: Status | None  # status-only items only
    step: float
    last_moved: date | None


@dataclass(frozen=True)
class StockView:
    rows: list[StockRow]
    checks: dict[str, PantryCheck]


@dataclass(frozen=True)
class Suggestion:
    item: Item
    name: str
    reason: str  # planned, low, out or usual
    quantity: str | None
    amount: float | None


@dataclass(frozen=True)
class ReportRow:
    item: Item
    name: str
    purchased: float
    logged: float
    wasted: float
    corrected: float
    shortfall: float
    level: float | None
    spend_cents: int | None


@dataclass(frozen=True)
class Report:
    start: date
    end: date
    rows: list[ReportRow]
    spend_cents: int


@dataclass(frozen=True)
class Summary:
    in_stock: list[StockRow]
    low: list[str]
    out: list[str]


# --- reading ----------------------------------------------------------------------------------


def levels(
    db: Session, household_id: uuid.UUID, item_ids: Iterable[uuid.UUID] | None = None
) -> dict[uuid.UUID, float]:
    """The level of each item: the sum of its movements (may be below zero; shown as zero)."""
    query = (
        select(StockMovement.item_id, func.sum(StockMovement.amount))
        .where(StockMovement.household_id == household_id)
        .group_by(StockMovement.item_id)
    )
    if item_ids is not None:
        query = query.where(StockMovement.item_id.in_(list(item_ids)))
    return {item_id: float(total) for item_id, total in db.execute(query)}


def _statuses(
    db: Session, household_id: uuid.UUID, item_ids: Iterable[uuid.UUID] | None = None
) -> dict[uuid.UUID, StockStatus]:
    query = select(StockStatus).where(StockStatus.household_id == household_id)
    if item_ids is not None:
        query = query.where(StockStatus.item_id.in_(list(item_ids)))
    return {s.item_id: s for s in db.scalars(query)}


def mode_of(item: Item, status: StockStatus | None) -> TrackingMode:
    """The household's choice for this item, else the item's own."""
    return TrackingMode(status.mode if status and status.mode else item.tracking_mode)


def _first_serving(item: Item) -> float | None:
    return item.servings[0].amount if item.servings else None


def _row(
    item: Item, status: StockStatus | None, level: float, last: date | None, language: str
) -> StockRow:
    mode = mode_of(item, status)
    counted = mode == TrackingMode.COUNTED
    return StockRow(
        item=item,
        name=items.name_of(item, language),
        mode=mode,
        level=rules.shown(level) if counted else None,
        status=None if counted else Status(status.status if status and status.status else "ok"),
        step=rules.step(package_size=item.package_size, serving=_first_serving(item)),
        last_moved=last,
    )


def _aisle_order(row: StockRow) -> tuple[int, str]:
    category = row.item.category
    aisles = list_rules.AISLES
    return (aisles.index(category) if category in aisles else len(aisles), row.name.lower())


def get_stock(
    db: Session, actor: Actor, *, language: str = "de", category: str | None = None
) -> StockView:
    """What is in the house, aisle by aisle: counted items with an amount or a recent movement,
    and status-only items the household has a status for."""
    household = actor.household_id
    since = today_for(db.get_one(User, actor.user_id)) - timedelta(days=RECENT_DAYS)
    moved = {
        item_id: (float(total), last)
        for item_id, total, last in db.execute(
            select(
                StockMovement.item_id,
                func.sum(StockMovement.amount),
                func.max(StockMovement.day),
            )
            .where(StockMovement.household_id == household)
            .group_by(StockMovement.item_id)
        )
    }
    statuses = _statuses(db, household)
    ids = set(moved) | set(statuses)
    found = _items(db, ids)
    rows = []
    for item_id in ids:
        item = found.get(item_id)
        if item is None or (category is not None and item.category != category):
            continue
        total, last = moved.get(item_id, (0.0, None))
        row = _row(item, statuses.get(item_id), total, last, language)
        stale = last is None or last < since
        if row.mode == TrackingMode.COUNTED and (row.level or 0) <= _EPSILON and stale:
            continue
        rows.append(row)
    rows.sort(key=_aisle_order)
    checks = {
        c.category: c
        for c in db.scalars(select(PantryCheck).where(PantryCheck.household_id == household))
    }
    return StockView(rows=rows, checks=checks)


def _items(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Item]:
    wanted = list(ids)
    if not wanted:
        return {}
    return {
        i.id: i
        for i in db.scalars(
            select(Item).where(Item.id.in_(wanted)).options(selectinload(Item.servings))
        )
    }


def item_stock(db: Session, actor: Actor, item_id: uuid.UUID, *, language: str = "de") -> StockRow:
    item = items.get(db, actor, item_id)
    status = _statuses(db, actor.household_id, [item.id]).get(item.id)
    last = db.scalar(
        select(func.max(StockMovement.day)).where(
            StockMovement.household_id == actor.household_id, StockMovement.item_id == item.id
        )
    )
    level = levels(db, actor.household_id, [item.id]).get(item.id, 0.0)
    return _row(item, status, level, last, language)


def movements(
    db: Session, actor: Actor, item_id: uuid.UUID, *, limit: int = 30
) -> list[StockMovement]:
    """The latest movements of one item, newest first: where its level comes from."""
    item = items.get(db, actor, item_id)
    return list(
        db.scalars(
            select(StockMovement)
            .where(
                StockMovement.household_id == actor.household_id,
                StockMovement.item_id == item.id,
            )
            .order_by(StockMovement.day.desc(), StockMovement.created_at.desc())
            .limit(limit)
        )
    )


def available(db: Session, actor: Actor, wanted: Iterable[Item]) -> dict[uuid.UUID, float]:
    """How much of each item is there to cook with: the level of a counted item, and for a
    status-only item all of it (infinity) once marked ok, nothing when unknown, low or out."""
    found = {i.id: i for i in wanted}
    statuses = _statuses(db, actor.household_id, found)
    now = levels(db, actor.household_id, found)
    result: dict[uuid.UUID, float] = {}
    for item_id, item in found.items():
        status = statuses.get(item_id)
        if mode_of(item, status) == TrackingMode.COUNTED:
            result[item_id] = rules.shown(now.get(item_id, 0.0))
        else:
            ok = status is not None and status.status == Status.OK
            result[item_id] = float("inf") if ok else 0.0
    return result


def summary(db: Session, actor: Actor, *, language: str = "de") -> Summary:
    """For 'what should we cook tonight': what is in stock, and the staples running low."""
    view = get_stock(db, actor, language=language)
    return Summary(
        in_stock=[r for r in view.rows if r.level is not None and r.level > _EPSILON],
        low=[r.name for r in view.rows if r.status == Status.LOW],
        out=[r.name for r in view.rows if r.status == Status.OUT],
    )


# --- purchases --------------------------------------------------------------------------------


def _move(
    db: Session,
    actor: Actor,
    item_id: uuid.UUID,
    amount: float,
    *,
    reason: Reason,
    source: Source,
    day: date,
    source_id: uuid.UUID | None = None,
) -> None:
    if abs(amount) < _EPSILON:
        return
    db.add(
        StockMovement(
            household_id=actor.household_id,
            item_id=item_id,
            amount=amount,
            reason=reason.value,
            source=source.value,
            source_id=source_id,
            day=day,
            created_by=actor.user_id,
        )
    )


def _status_row(db: Session, actor: Actor, item_id: uuid.UUID) -> StockStatus:
    row = db.get(StockStatus, (actor.household_id, item_id))
    if row is None:
        row = StockStatus(household_id=actor.household_id, item_id=item_id)
        db.add(row)
    row.updated_at = clock.now()
    row.updated_by = actor.user_id
    return row


def _price(cents: int | None) -> int | None:
    if cents is not None and not 0 <= cents <= MAX_PRICE_CENTS:
        raise Invalid("price_invalid", max=MAX_PRICE_CENTS)
    return cents


def get_purchase(db: Session, actor: Actor, purchase_id: uuid.UUID) -> Purchase:
    purchase = db.scalars(
        select(Purchase)
        .where(Purchase.id == purchase_id)
        .options(selectinload(Purchase.lines).selectinload(PurchaseLine.item))
    ).first()
    if purchase is None or purchase.household_id != actor.household_id:
        raise NotFound("purchase_not_found")
    return purchase


def list_purchases(db: Session, actor: Actor, *, limit: int = 20) -> list[Purchase]:
    return list(
        db.scalars(
            select(Purchase)
            .where(Purchase.household_id == actor.household_id)
            .order_by(Purchase.day.desc(), Purchase.created_at.desc())
            .limit(limit)
            .options(selectinload(Purchase.lines).selectinload(PurchaseLine.item))
        )
    )


def record_purchase(
    db: Session, actor: Actor, data: PurchaseInput, *, language: str = "de"
) -> Purchase:
    """One shop. Food goes into stock and the list items it came from leave the list. The id
    is made by the phone: the same purchase sent again is recorded once."""
    existing = db.get(Purchase, data.id)
    if existing is not None:
        return get_purchase(db, actor, existing.id)  # another household's id is not found
    if not data.lines:
        raise Invalid("purchase_empty")
    if len(data.lines) > MAX_LINES:
        raise Invalid("purchase_too_long", max=MAX_LINES)
    today = today_for(db.get_one(User, actor.user_id))
    day = rules.check_purchase_day(data.day or today, today=today)
    store = shopping.get_store(db, actor, data.store_id) if data.store_id else None
    purchase = Purchase(
        id=data.id,
        household_id=actor.household_id,
        store_id=store.id if store else None,
        day=day,
        created_by=actor.user_id,
    )
    db.add(purchase)
    listed = _listed(db, actor, [line.list_item_id for line in data.lines])
    bought: list[ShoppingListItem] = []
    for position, line in enumerate(data.lines):
        row = listed.get(line.list_item_id) if line.list_item_id else None
        item_id = line.item_id or (row.item_id if row else None)
        item = items.get(db, actor, item_id) if item_id else None
        text = (line.text or "").strip() or (
            row.text if row else items.name_of(item, language) if item else ""
        )
        quantity = list_rules.check_quantity(
            line.quantity if line.quantity is not None else row.quantity if row else None
        )
        amount = (
            rules.check_amount(line.amount)
            if line.amount is not None
            else rules.amount_from_quantity(
                quantity,
                base_unit=item.base_unit,
                package_size=item.package_size,
                serving=_first_serving(item),
            )
            if item
            else None
        )
        purchase.lines.append(
            PurchaseLine(
                item_id=item.id if item else None,
                text=list_rules.check_text(text),
                quantity=quantity,
                amount=amount or None,
                price_cents=_price(line.price_cents),
                list_item_id=row.id if row else None,
                position=position,
            )
        )
        if row is not None:
            bought.append(row)
    db.flush()
    statuses = _statuses(db, actor.household_id, [ln.item.id for ln in purchase.lines if ln.item])
    for ln in purchase.lines:
        if ln.item is None:
            continue
        if mode_of(ln.item, statuses.get(ln.item.id)) == TrackingMode.STATUS:
            _status_row(db, actor, ln.item.id).status = Status.OK.value
        elif ln.amount:
            _move(
                db,
                actor,
                ln.item.id,
                ln.amount,
                reason=Reason.PURCHASE,
                source=Source.PURCHASE,
                day=day,
                source_id=ln.id,
            )
    shopping.remove_rows(db, actor, bought)
    priced = [ln.price_cents for ln in purchase.lines if ln.price_cents is not None]
    audit.record(
        db,
        actor=actor,
        entity="purchase",
        entity_id=purchase.id,
        action="create",
        after={
            "day": day.isoformat(),
            "store_id": str(purchase.store_id) if purchase.store_id else None,
            "lines": len(purchase.lines),
            "spend_cents": sum(priced) if priced else None,
        },
    )
    db.commit()
    return get_purchase(db, actor, purchase.id)


def _listed(
    db: Session, actor: Actor, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, ShoppingListItem]:
    """The open list items a purchase came from. One already gone (the partner bought it, or the
    same purchase arrives again) is simply not there."""
    wanted = [i for i in ids if i is not None]
    if not wanted:
        return {}
    return {
        r.id: r
        for r in db.scalars(
            select(ShoppingListItem).where(
                ShoppingListItem.id.in_(wanted),
                ShoppingListItem.household_id == actor.household_id,
                ShoppingListItem.deleted_at.is_(None),
            )
        )
    }


# --- meals ------------------------------------------------------------------------------------


def _wanted(db: Session, entry: MealEntry) -> dict[uuid.UUID, float]:
    """What an entry takes out of stock now: the whole dish once someone has eaten it, counted
    items only."""
    eaten = any(p.state == EntryState.LOGGED for p in entry.participants)
    use = rules.consumption(
        [(c.item_id, c.amount) for c in entry.components], eaten=eaten, eaten_out=entry.eaten_out
    )
    if not use:
        return {}
    statuses = _statuses(db, entry.household_id, use)
    found = {c.item_id: c.item for c in entry.components if c.item is not None}
    return {
        item_id: amount
        for item_id, amount in use.items()
        if item_id in found
        and mode_of(found[item_id], statuses.get(item_id)) == TrackingMode.COUNTED
    }


def sync_entry(db: Session, actor: Actor, entry_id: uuid.UUID, entry: MealEntry | None) -> None:
    """Bring a meal's stock movements in line with the meal (None: it is gone). Called by the
    day service on every change of an entry, inside its transaction."""
    booked: dict[tuple[uuid.UUID, date], float] = {}
    short: dict[tuple[uuid.UUID, date], float] = {}
    for m in db.scalars(
        select(StockMovement).where(
            StockMovement.household_id == actor.household_id,
            StockMovement.source_id == entry_id,
            StockMovement.source.in_([Source.ENTRY.value, Source.SHORTFALL.value]),
        )
    ):
        into = booked if m.source == Source.ENTRY else short
        into[(m.item_id, m.day)] = into.get((m.item_id, m.day), 0.0) + m.amount
    wanted = _wanted(db, entry) if entry is not None else {}
    if not booked and not wanted:
        return
    day = entry.day if entry is not None else date.min
    involved = {item for item, _ in booked} | set(wanted)
    changes = rules.sync_entry(
        booked=booked,
        shortfalls=short,
        wanted=wanted,
        day=day,
        levels=levels(db, actor.household_id, involved),
    )
    for c in changes:
        assert isinstance(c.item, uuid.UUID)
        _move(
            db,
            actor,
            c.item,
            c.amount,
            reason=Reason.CONSUMPTION if c.source == Source.ENTRY else Reason.CORRECTION,
            source=c.source,
            day=c.day,
            source_id=entry_id,
        )
    if changes:
        audit.record(
            db,
            actor=actor,
            entity="stock",
            entity_id=entry_id,
            action="meal",
            after={"movements": len(changes)},
        )


# --- by hand ----------------------------------------------------------------------------------


def _today(db: Session, actor: Actor) -> date:
    return today_for(db.get_one(User, actor.user_id))


def _count(
    db: Session, actor: Actor, item: Item, counted: float, *, source: Source, day: date
) -> float:
    now = levels(db, actor.household_id, [item.id]).get(item.id, 0.0)
    # Counting what is there: a level below zero (never shown) is taken as zero.
    change = rules.correction(level_now=rules.shown(now), counted=counted)
    if now < 0:
        change -= now
    _move(db, actor, item.id, change, reason=Reason.CORRECTION, source=source, day=day)
    return change


def adjust(
    db: Session,
    actor: Actor,
    item_id: uuid.UUID,
    *,
    count: float | None = None,
    waste: float | None = None,
    add: float | None = None,
    status: Status | None = None,
    language: str = "de",
) -> StockRow:
    """Fix one item by hand: what is there now (`count`), what was thrown away (`waste`), found
    more (`add`), or the status of a status-only item. Exactly one of them."""
    given = [v for v in (count, waste, add, status) if v is not None]
    if len(given) != 1:
        raise Invalid("stock_change_invalid")
    item = items.get(db, actor, item_id)
    today = _today(db, actor)
    before: dict[str, Any]
    after: dict[str, Any]
    if status is not None:
        row = _status_row(db, actor, item.id)
        before, after = {"status": row.status}, {"status": Status(status).value}
        row.status = Status(status).value
    elif count is not None:
        change = _count(db, actor, item, count, source=Source.MANUAL, day=today)
        before, after = {"level": count - change}, {"level": count}
    elif waste is not None:
        now = levels(db, actor.household_id, [item.id]).get(item.id, 0.0)
        change = rules.waste(level_now=now, amount=waste)
        _move(db, actor, item.id, change, reason=Reason.WASTE, source=Source.MANUAL, day=today)
        before, after = {"level": rules.shown(now)}, {"waste": -change}
    else:
        assert add is not None
        if add <= 0:
            raise Invalid("stock_amount_invalid", max=rules.MAX_STOCK)
        rules.check_amount(add)
        _move(db, actor, item.id, add, reason=Reason.CORRECTION, source=Source.MANUAL, day=today)
        before, after = {}, {"add": add}
    audit.record(
        db,
        actor=actor,
        entity="stock",
        entity_id=item.id,
        action="adjust",
        before=before,
        after=after,
    )
    db.commit()
    return item_stock(db, actor, item.id, language=language)


def set_mode(
    db: Session,
    actor: Actor,
    item_id: uuid.UUID,
    mode: TrackingMode | None,
    *,
    language: str = "de",
) -> StockRow:
    """Track this item by amount or by status in this household (None: as the item says)."""
    item = items.get(db, actor, item_id)
    row = _status_row(db, actor, item.id)
    before = row.mode
    row.mode = TrackingMode(mode).value if mode is not None else None
    if mode_of(item, row) == TrackingMode.STATUS and row.status is None:
        row.status = Status.OK.value
    audit.record(
        db,
        actor=actor,
        entity="stock",
        entity_id=item.id,
        action="mode",
        before={"mode": before},
        after={"mode": row.mode},
    )
    db.commit()
    return item_stock(db, actor, item.id, language=language)


def check_category(
    db: Session,
    actor: Actor,
    category: str,
    *,
    counts: Mapping[uuid.UUID, float] | None = None,
    statuses: Mapping[uuid.UUID, Status] | None = None,
) -> PantryCheck:
    """The pantry check of one aisle: the amounts and statuses fixed on the way, and the aisle
    marked as checked, all at once."""
    try:
        aisle = Category(category).value
    except ValueError as err:
        raise Invalid("category_unknown") from err
    counts, statuses = dict(counts or {}), dict(statuses or {})
    if len(counts) + len(statuses) > MAX_CHECK_ITEMS:
        raise Invalid("too_many_operations", max=MAX_CHECK_ITEMS)
    today = _today(db, actor)
    changed = 0
    for item_id, counted in counts.items():
        item = items.get(db, actor, item_id)
        if abs(_count(db, actor, item, counted, source=Source.PANTRY, day=today)) > _EPSILON:
            changed += 1
    for item_id, status in statuses.items():
        item = items.get(db, actor, item_id)
        _status_row(db, actor, item.id).status = Status(status).value
        changed += 1
    check = db.get(PantryCheck, (actor.household_id, aisle))
    if check is None:
        check = PantryCheck(household_id=actor.household_id, category=aisle)
        db.add(check)
    check.checked_at = clock.now()
    check.checked_by = actor.user_id
    audit.record(
        db,
        actor=actor,
        entity="stock",
        entity_id=None,
        action="pantry_check",
        after={"category": aisle, "changed": changed},
    )
    db.commit()
    return check


# --- the list ---------------------------------------------------------------------------------


def _plan_days(db: Session, actor: Actor) -> int:
    profile = db.get(Profile, actor.user_id)
    return profile.list_plan_days if profile else rules.PLAN_DAYS_DEFAULT


def set_plan_days(db: Session, actor: Actor, days: int) -> int:
    """How many days of plans the list suggestions look ahead (for this person)."""
    profile = db.get_one(Profile, actor.user_id)
    before = profile.list_plan_days
    profile.list_plan_days = rules.check_plan_days(days)
    if before != days:
        profile.updated_at = clock.now()
        audit.record(
            db,
            actor=actor,
            entity="profile",
            entity_id=actor.user_id,
            action="updated",
            before={"list_plan_days": before},
            after={"list_plan_days": days},
        )
        db.commit()
    return days


def suggestions(db: Session, actor: Actor, *, language: str = "de") -> list[Suggestion]:
    """The 'Suggested' section under the list; it never adds anything by itself. First what
    planned meals need beyond what is in stock, then staples marked low or out, then usual
    purchases that are not in stock. Items already on the list are left out."""
    household = actor.household_id
    today = _today(db, actor)
    on_list = {
        r.item_id
        for r in db.scalars(
            select(ShoppingListItem).where(
                ShoppingListItem.household_id == household, ShoppingListItem.deleted_at.is_(None)
            )
        )
        if r.item_id is not None
    }
    statuses = _statuses(db, household)
    result: list[Suggestion] = []
    seen = set(on_list)

    # 1. Planned meals in the coming days, eaten at home and not eaten yet.
    end = today + timedelta(days=_plan_days(db, actor) - 1)
    planned = db.scalars(
        select(MealEntry)
        .where(
            MealEntry.household_id == household,
            MealEntry.day.between(today, end),
            MealEntry.eaten_out.is_(False),
        )
        .options(
            selectinload(MealEntry.components)
            .selectinload(MealComponent.item)
            .selectinload(Item.servings),
            selectinload(MealEntry.participants),
        )
    )
    needs: dict[uuid.UUID, float] = {}
    found: dict[uuid.UUID, Item] = {}
    for entry in planned:
        states = {p.state for p in entry.participants}
        if EntryState.LOGGED in states or EntryState.PLANNED not in states:
            continue
        for c in entry.components:
            if c.item is None or not c.amount:
                continue
            if mode_of(c.item, statuses.get(c.item.id)) != TrackingMode.COUNTED:
                continue
            found[c.item.id] = c.item
            needs[c.item.id] = needs.get(c.item.id, 0.0) + c.amount
    have = levels(db, household, needs)
    for item_id, lack in rules.missing(needs, have).items():
        if item_id in seen:
            continue
        item = found[item_id]
        seen.add(item_id)
        result.append(
            Suggestion(
                item=item,
                name=items.name_of(item, language),
                reason="planned",
                quantity=recipe_rules.quantity_text(lack, item.base_unit, language),
                amount=lack,
            )
        )

    # 2. Staples marked low or out.
    flagged = [
        s
        for s in statuses.values()
        if s.status in (Status.LOW, Status.OUT) and s.item_id not in seen
    ]
    flagged_items = _items(db, (s.item_id for s in flagged))
    for s in sorted(flagged, key=lambda s: (s.status != Status.OUT, s.updated_at)):
        item = flagged_items[s.item_id]
        if mode_of(item, s) != TrackingMode.STATUS:
            continue
        seen.add(item.id)
        result.append(
            Suggestion(
                item=item,
                name=items.name_of(item, language),
                reason=s.status or "low",
                quantity=None,
                amount=None,
            )
        )

    # 3. Usual purchases that are not in stock.
    since = today - timedelta(days=rules.USUAL_WINDOW_DAYS)
    bought = {
        item_id: count
        for item_id, count in db.execute(
            select(PurchaseLine.item_id, func.count(func.distinct(PurchaseLine.purchase_id)))
            .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
            .where(
                Purchase.household_id == household,
                Purchase.day >= since,
                PurchaseLine.item_id.is_not(None),
            )
            .group_by(PurchaseLine.item_id)
        )
        if item_id is not None and item_id not in seen and rules.is_usual(purchases=count)
    }
    if bought:
        stock_now = levels(db, household, bought)
        usual_items = _items(db, bought)
        last = _last_quantities(db, household, bought)
        for item_id, _ in sorted(bought.items(), key=lambda kv: -kv[1]):
            usual = usual_items.get(item_id)
            if usual is None or mode_of(usual, statuses.get(item_id)) != TrackingMode.COUNTED:
                continue
            if rules.shown(stock_now.get(item_id, 0.0)) > _EPSILON:
                continue
            result.append(
                Suggestion(
                    item=usual,
                    name=items.name_of(usual, language),
                    reason="usual",
                    quantity=last.get(item_id),
                    amount=None,
                )
            )
    return result


def _last_quantities(
    db: Session, household_id: uuid.UUID, item_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """The quantity of each item's latest purchase, for suggesting the usual amount."""
    rows = db.execute(
        select(PurchaseLine.item_id, PurchaseLine.quantity)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.household_id == household_id, PurchaseLine.item_id.in_(list(item_ids)))
        .order_by(Purchase.day, Purchase.created_at)
    )
    return {item_id: quantity for item_id, quantity in rows if item_id is not None}


# --- report -----------------------------------------------------------------------------------


def report(db: Session, actor: Actor, *, start: date, end: date, language: str = "de") -> Report:
    """Purchased, logged, wasted and corrected amounts per item over a period, with the spend
    where prices were entered. Items most bought first."""
    if end < start or (end - start).days + 1 > MAX_REPORT_DAYS:
        raise Invalid("range_invalid", max=MAX_REPORT_DAYS)
    household = actor.household_id
    moved = db.scalars(
        select(StockMovement).where(
            StockMovement.household_id == household, StockMovement.day.between(start, end)
        )
    )
    sums = rules.report(
        rules.Movement(
            item=m.item_id,
            reason=Reason(m.reason),
            source=Source(m.source),
            amount=m.amount,
            day=m.day,
        )
        for m in moved
    )
    spend: dict[uuid.UUID | None, int] = {}
    for item_id, cents in db.execute(
        select(PurchaseLine.item_id, func.sum(PurchaseLine.price_cents))
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(
            Purchase.household_id == household,
            Purchase.day.between(start, end),
            PurchaseLine.price_cents.is_not(None),
        )
        .group_by(PurchaseLine.item_id)
    ):
        spend[item_id] = int(cents or 0)
    ids = {i for i in sums if isinstance(i, uuid.UUID)} | {i for i in spend if i is not None}
    found = _items(db, ids)
    statuses = _statuses(db, household, ids)
    now = levels(db, household, ids)
    rows = []
    for item_id in ids:
        item = found.get(item_id)
        if item is None:
            continue
        s = sums.get(item_id, rules.ItemReport())
        counted = mode_of(item, statuses.get(item_id)) == TrackingMode.COUNTED
        rows.append(
            ReportRow(
                item=item,
                name=items.name_of(item, language),
                purchased=s.purchased,
                logged=s.logged,
                wasted=s.wasted,
                corrected=s.corrected,
                shortfall=s.shortfall,
                level=rules.shown(now.get(item_id, 0.0)) if counted else None,
                spend_cents=spend.get(item_id),
            )
        )
    rows.sort(key=lambda r: (-r.purchased, -r.logged, r.name.lower()))
    return Report(start=start, end=end, rows=rows, spend_cents=sum(spend.values()))
