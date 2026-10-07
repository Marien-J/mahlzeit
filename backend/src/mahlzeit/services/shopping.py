"""The household's shared shopping list.

Every change arrives as an operation with a client-made item id and the time it was made, so
phones can queue changes offline and send them again without duplicates (see domain.shopping).
The UI sends batches of operations; tools call the same `apply`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.domain import shopping as rules
from mahlzeit.domain.catalogue import Category
from mahlzeit.domain.errors import Conflict, DomainError, Invalid, NotFound
from mahlzeit.domain.permissions import Actor, require_household
from mahlzeit.domain.search import normalize
from mahlzeit.models import Item, ListMemory, ShoppingListItem, Store
from mahlzeit.services import audit, items

MAX_OPS = 200
HISTORY_LIMIT = 500
ENTITY = "list_item"

OpKind = Literal["add", "update", "remove"]
Status = Literal["applied", "unchanged", "removed", "not_found", "invalid"]


@dataclass(frozen=True)
class Op:
    kind: OpKind
    id: uuid.UUID
    at: datetime | None = None
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpResult:
    id: uuid.UUID
    status: Status
    code: str | None = None


# --- reading ------------------------------------------------------------------------------


def open_items(db: Session, actor: Actor) -> list[ShoppingListItem]:
    """The list as it is now: aisle by aisle, checked items at the bottom."""
    rows = list(
        db.scalars(
            select(ShoppingListItem).where(
                ShoppingListItem.household_id == actor.household_id,
                ShoppingListItem.deleted_at.is_(None),
            )
        )
    )
    keyed = {r.id: r for r in rows}
    order = rules.ordered(
        rules.Row(key=r.id, category=r.category, checked=r.checked, added=r.created_at)
        for r in rows
    )
    return [keyed[o.key] for o in order]


def stores(db: Session, actor: Actor) -> list[Store]:
    return list(
        db.scalars(
            select(Store)
            .where(or_(Store.household_id.is_(None), Store.household_id == actor.household_id))
            .order_by(Store.position, func.lower(Store.name))
        )
    )


def history(db: Session, actor: Actor, *, limit: int = HISTORY_LIMIT) -> list[ListMemory]:
    """What the household has put on its list before, most used first: the source of
    suggestions while typing, which the phone keeps for offline use."""
    return list(
        db.scalars(
            select(ListMemory)
            .where(ListMemory.household_id == actor.household_id)
            .order_by(ListMemory.uses.desc(), ListMemory.last_used_at.desc())
            .limit(limit)
        )
    )


# --- stores -------------------------------------------------------------------------------


def get_store(db: Session, actor: Actor, store_id: uuid.UUID) -> Store:
    store = db.get(Store, store_id)
    if store is None or (
        store.household_id is not None and store.household_id != actor.household_id
    ):
        raise NotFound("store_not_found")
    return store


def create_store(db: Session, actor: Actor, name: str) -> Store:
    cleaned = rules.check_store_name(name)
    taken = db.scalars(
        select(Store).where(
            Store.household_id == actor.household_id, func.lower(Store.name) == cleaned.lower()
        )
    ).first()
    if taken is not None:
        raise Conflict("store_name_taken", name=cleaned)
    store = Store(household_id=actor.household_id, name=cleaned)
    db.add(store)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity="store",
        entity_id=store.id,
        action="create",
        after={"name": cleaned},
    )
    db.commit()
    return store


def delete_store(db: Session, actor: Actor, store_id: uuid.UUID) -> None:
    """Custom stores only; list items and memories that used it keep no store."""
    store = get_store(db, actor, store_id)
    if store.household_id is None:
        raise Invalid("store_builtin")
    audit.record(
        db,
        actor=actor,
        entity="store",
        entity_id=store.id,
        action="delete",
        before={"name": store.name},
    )
    db.delete(store)
    db.commit()


# --- writing ------------------------------------------------------------------------------


def _memory_key(item_id: uuid.UUID | None, text: str) -> str:
    return f"item:{item_id}" if item_id else f"text:{normalize(text)}"[:160]


def _memory(db: Session, actor: Actor, key: str) -> ListMemory | None:
    return db.scalars(
        select(ListMemory).where(
            ListMemory.household_id == actor.household_id, ListMemory.key == key
        )
    ).first()


def _remember(
    db: Session,
    actor: Actor,
    row: ShoppingListItem,
    *,
    used: bool,
    now: datetime,
) -> None:
    key = _memory_key(row.item_id, row.text)
    memory = _memory(db, actor, key)
    if memory is None:
        memory = ListMemory(household_id=actor.household_id, key=key, uses=0)
        db.add(memory)
    memory.text = row.text
    memory.item_id = row.item_id
    memory.category = row.category
    memory.store_id = row.store_id
    if used:
        memory.uses = (memory.uses or 0) + 1
        memory.last_used_at = now


def _category(value: Any) -> str:
    try:
        return Category(str(value)).value
    except ValueError as err:
        raise Invalid("category_unknown") from err


def _clean(db: Session, actor: Actor, fields: dict[str, Any]) -> dict[str, Any]:
    """Validate the fields of an add or update. Unknown fields are refused."""
    unknown = set(fields) - rules.FIELDS
    if unknown:
        raise Invalid("list_field_unknown", fields=sorted(unknown))
    clean: dict[str, Any] = {}
    for name, value in fields.items():
        match name:
            case "text":
                clean[name] = rules.check_text(str(value or ""))
            case "quantity":
                clean[name] = rules.check_quantity(value)
            case "category":
                clean[name] = _category(value)
            case "checked":
                clean[name] = bool(value)
            case "store_id":
                clean[name] = get_store(db, actor, _uuid(value)).id if value else None
            case "item_id":
                clean[name] = items.get(db, actor, _uuid(value)).id if value else None
    return clean


def _uuid(value: Any) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError as err:
        raise Invalid("id_invalid") from err


def _snapshot(row: ShoppingListItem) -> dict[str, Any]:
    return {
        "text": row.text,
        "quantity": row.quantity,
        "category": row.category,
        "store_id": str(row.store_id) if row.store_id else None,
        "checked": row.checked,
    }


def _add(
    db: Session,
    actor: Actor,
    op: Op,
    at: datetime,
    now: datetime,
    language: str,
    origin: str,
) -> Status:
    fields = dict(op.fields)
    parse = fields.pop("parse", True) is not False
    clean = _clean(db, actor, fields)
    item: Item | None = items.get(db, actor, clean["item_id"]) if clean.get("item_id") else None
    if "text" not in clean:
        if item is None:
            raise Invalid("list_text_empty")
        clean["text"] = rules.check_text(items.name_of(item, language))
    if parse and clean.get("quantity") is None and item is None:
        entry = rules.parse_entry(clean["text"])
        clean["text"], clean["quantity"] = entry.name, entry.quantity
    memory = _memory(db, actor, _memory_key(clean.get("item_id"), clean["text"]))
    if "category" not in clean:
        clean["category"] = (
            memory.category if memory else item.category if item else Category.OTHER.value
        )
    if "store_id" not in clean and memory is not None:
        clean["store_id"] = memory.store_id
    checked = bool(clean.get("checked", False))
    row = ShoppingListItem(
        id=op.id,
        household_id=actor.household_id,
        text=clean["text"],
        item_id=clean.get("item_id"),
        quantity=clean.get("quantity"),
        store_id=clean.get("store_id"),
        category=clean["category"],
        checked=checked,
        checked_at=at if checked else None,
        checked_by=actor.user_id if checked else None,
        origin=origin,
        field_times={name: at.isoformat() for name in rules.FIELDS},
        created_by=actor.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _remember(db, actor, row, used=True, now=now)
    audit.record(
        db, actor=actor, entity=ENTITY, entity_id=row.id, action="add", after=_snapshot(row)
    )
    return "applied"


def _update(
    db: Session, actor: Actor, row: ShoppingListItem, op: Op, at: datetime, now: datetime
) -> Status:
    fields = {k: v for k, v in op.fields.items() if k not in ("parse", "item_id")}
    clean = _clean(db, actor, fields)
    before = _snapshot(row)
    state = rules.FieldState(
        values={name: getattr(row, name) for name in rules.FIELDS},
        times={k: datetime.fromisoformat(v) for k, v in (row.field_times or {}).items()},
    )
    result = rules.merge(state, clean, at=at, now=now)
    row.field_times = {k: v.isoformat() for k, v in result.state.times.items()}
    if not result.changed:
        return "unchanged"
    for name in result.changed:
        setattr(row, name, result.state.values[name])
    if "checked" in result.changed:
        row.checked_at = at if row.checked else None  # when it was ticked, also offline
        row.checked_by = actor.user_id if row.checked else None
    row.updated_at = now
    if result.changed & {"category", "store_id"}:
        _remember(db, actor, row, used=False, now=now)
    action = ("check" if row.checked else "uncheck") if result.changed == {"checked"} else "update"
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=row.id,
        action=action,
        before=before,
        after=_snapshot(row),
    )
    return "applied"


def _remove(db: Session, actor: Actor, row: ShoppingListItem, now: datetime) -> Status:
    row.deleted_at = now
    row.deleted_by = actor.user_id
    row.updated_at = now
    audit.record(
        db, actor=actor, entity=ENTITY, entity_id=row.id, action="remove", before=_snapshot(row)
    )
    return "applied"


def _one(db: Session, actor: Actor, op: Op, now: datetime, language: str, origin: str) -> Status:
    at = op.at or now
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    at = min(at, now)  # a phone clock ahead of the server counts as now
    row = db.get(ShoppingListItem, op.id)
    if row is not None and row.household_id != actor.household_id:
        return "not_found"
    if row is not None and row.deleted_at is not None:
        return "removed"  # removing is final; late edits and re-sent adds are ignored
    match op.kind:
        case "add":
            # The same add sent again (a retry after a lost answer) changes nothing.
            return "unchanged" if row else _add(db, actor, op, at, now, language, origin)
        case "update":
            return _update(db, actor, row, op, at, now) if row else "not_found"
        case "remove":
            return _remove(db, actor, row, now) if row else "removed"


def apply(
    db: Session, actor: Actor, ops: Sequence[Op], *, language: str = "de", origin: str = "manual"
) -> list[OpResult]:
    """Apply operations in order. Each one stands alone: a bad operation is reported and
    skipped, so one broken change can never block a phone's queue."""
    if len(ops) > MAX_OPS:
        raise Invalid("too_many_operations", max=MAX_OPS)
    now = clock.now()
    results = []
    for op in ops:
        try:
            with db.begin_nested():
                status = _one(db, actor, op, now, language, origin)
            results.append(OpResult(op.id, status))
        except DomainError as err:
            results.append(OpResult(op.id, "invalid", err.code))
    db.commit()
    return results


def remove_rows(db: Session, actor: Actor, rows: Sequence[ShoppingListItem]) -> None:
    """Take bought items off the list (inside the purchase's transaction)."""
    now = clock.now()
    for row in rows:
        if row.household_id == actor.household_id and row.deleted_at is None:
            _remove(db, actor, row, now)


# --- conveniences for tools ---------------------------------------------------------------


def get_row(db: Session, actor: Actor, item_id: uuid.UUID) -> ShoppingListItem:
    row = db.get(ShoppingListItem, item_id)
    if row is None or row.deleted_at is not None:
        raise NotFound("list_item_not_found")
    require_household(actor, row.household_id)
    return row
