"""Output shapes shared by the REST API and the connector tools, so both answer the same way.

Names follow the reader's language with the brief's fallback (their language, German, English).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel

from mahlzeit import clock
from mahlzeit.domain.catalogue import display_name
from mahlzeit.domain.nutrition import Nutrients, Totals, rounded
from mahlzeit.domain.off import ItemDraft
from mahlzeit.domain.targets import Targets
from mahlzeit.models import (
    Item,
    ListMemory,
    MealComponent,
    MealEntry,
    Recipe,
    ShoppingListItem,
    Store,
)
from mahlzeit.services import day as day_service
from mahlzeit.services import items as item_service
from mahlzeit.services import saved_meals
from mahlzeit.services import shopping as shopping_service
from mahlzeit.services.snapshot import Snapshot
from mahlzeit.services.targets import TargetPlan


class NutrientsOut(BaseModel):
    kcal: float | None
    protein: float | None
    carbs: float | None
    sugar: float | None
    fat: float | None
    sat_fat: float | None
    fibre: float | None
    salt: float | None
    alcohol: float | None


class TotalsOut(BaseModel):
    values: NutrientsOut
    incomplete: list[str]


class TargetsOut(BaseModel):
    kcal: float | None
    protein: float | None
    carbs: float | None
    fat: float | None


class ServingOut(BaseModel):
    label: str
    amount: float


class ItemOut(BaseModel):
    id: uuid.UUID
    name: str
    names: dict[str, str | None]
    brand: str | None
    category: str
    base_unit: Literal["g", "ml"]
    nutrients: NutrientsOut
    package_size: float | None
    servings: list[ServingOut]
    barcodes: list[str]
    tracking_mode: Literal["counted", "status"]
    source: str
    generic: bool
    favourite: bool
    image_url: str | None


class ItemDraftOut(BaseModel):
    barcode: str
    names: dict[str, str]
    brand: str | None
    category: str
    base_unit: Literal["g", "ml"]
    package_size: float | None
    servings: list[ServingOut]
    nutrients: NutrientsOut
    missing: list[str]
    complete: bool
    image_url: str | None


class BarcodeOut(BaseModel):
    status: Literal["item", "draft", "not_found"]
    item: ItemOut | None
    draft: ItemDraftOut | None


class ComponentOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID | None
    name: str
    amount: float | None
    base_unit: str | None
    serving_label: str | None
    serving_count: float | None
    quick: bool
    nutrients: NutrientsOut


class EntryOut(BaseModel):
    id: uuid.UUID
    day: date
    slot: Literal["breakfast", "lunch", "dinner", "snack"]
    at: time
    name: str | None
    eaten_out: bool
    saved_meal_id: uuid.UUID | None
    state: Literal["planned", "logged", "skipped"] | None
    share: float | None
    components: list[ComponentOut]
    intake: TotalsOut | None


class PersonDayOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    is_me: bool
    day_type: Literal["training", "rest"]
    targets: TargetsOut | None
    logged: TotalsOut
    planned: TotalsOut
    remaining: TargetsOut | None
    projection: TargetsOut | None
    entries: list[EntryOut]


class DayOut(BaseModel):
    day: date
    people: list[PersonDayOut]


class TargetSetOut(BaseModel):
    valid_from: date
    day_type: Literal["training", "rest"]
    targets: TargetsOut


class TargetPlanOut(BaseModel):
    week_pattern: str
    history: list[TargetSetOut]


class IngredientOut(BaseModel):
    item_id: uuid.UUID
    name: str
    amount: float
    base_unit: str


class SavedMealOut(BaseModel):
    id: uuid.UUID
    name: str
    ingredients: list[IngredientOut]
    per_serving: TotalsOut


class SnapshotOut(BaseModel):
    today: DayOut
    tonight: list[EntryOut]
    shopping_list: ListOut
    not_yet_available: list[str]


class ConnectorOut(BaseModel):
    active: bool
    created_at: datetime | None
    last_used_at: datetime | None


class ConnectorCreatedOut(BaseModel):
    url: str


class StoreOut(BaseModel):
    id: uuid.UUID
    key: str | None
    name: str | None
    custom: bool


class ListItemOut(BaseModel):
    id: uuid.UUID
    text: str
    item_id: uuid.UUID | None
    quantity: str | None
    store_id: uuid.UUID | None
    category: str
    checked: bool
    checked_at: datetime | None
    checked_by: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ListOut(BaseModel):
    items: list[ListItemOut]
    stores: list[StoreOut]
    server_time: datetime


class ListMemoryOut(BaseModel):
    text: str
    item_id: uuid.UUID | None
    category: str
    store_id: uuid.UUID | None
    uses: int


class ListOpResultOut(BaseModel):
    id: uuid.UUID
    status: Literal["applied", "unchanged", "removed", "not_found", "invalid"]
    code: str | None


class ListOpsOut(BaseModel):
    results: list[ListOpResultOut]
    list: ListOut


# --- converters ---------------------------------------------------------------------------


def nutrients(n: Nutrients) -> NutrientsOut:
    return NutrientsOut(**rounded(n).as_dict())


def totals(t: Totals) -> TotalsOut:
    return TotalsOut(values=nutrients(t.values), incomplete=sorted(t.incomplete))


def targets(t: Targets | None) -> TargetsOut | None:
    if t is None:
        return None

    def r(v: float | None, digits: int = 1) -> float | None:
        return None if v is None else round(v, digits)

    return TargetsOut(kcal=r(t.kcal, 0), protein=r(t.protein), carbs=r(t.carbs), fat=r(t.fat))


def _names(item: Item) -> dict[str, str | None]:
    return {"de": item.name_de, "en": item.name_en, "nl": item.name_nl}


def item(
    i: Item, language: str, favourites: set[uuid.UUID] | frozenset[uuid.UUID] = frozenset()
) -> ItemOut:
    return ItemOut(
        id=i.id,
        name=display_name(_names(i), language),
        names=_names(i),
        brand=i.brand,
        category=i.category,
        base_unit=i.base_unit,
        nutrients=nutrients(item_service.nutrients_of(i)),
        package_size=i.package_size,
        servings=[ServingOut(label=s.label, amount=s.amount) for s in i.servings],
        barcodes=[b.code for b in i.barcodes],
        tracking_mode=i.tracking_mode,
        source=i.source,
        generic=i.household_id is None,
        favourite=i.id in favourites,
        image_url=i.image_url,
    )


def draft(d: ItemDraft) -> ItemDraftOut:
    return ItemDraftOut(
        barcode=d.barcode,
        names=d.names,
        brand=d.brand,
        category=d.category.value,
        base_unit=d.base_unit.value,
        package_size=d.package_size,
        servings=[ServingOut(label=label, amount=amount) for label, amount in d.servings],
        nutrients=nutrients(d.nutrients),
        missing=d.missing,
        complete=d.complete,
        image_url=d.image_url,
    )


def barcode(
    result: item_service.BarcodeResult, language: str, favourites: set[uuid.UUID]
) -> BarcodeOut:
    return BarcodeOut(
        status=result.status,
        item=item(result.item, language, favourites) if result.item else None,
        draft=draft(result.draft) if result.draft else None,
    )


def component(c: MealComponent, language: str) -> ComponentOut:
    name = display_name(_names(c.item), language) if c.item else (c.quick_name or "")
    return ComponentOut(
        id=c.id,
        item_id=c.item_id,
        name=name,
        amount=c.amount,
        base_unit=c.item.base_unit if c.item else None,
        serving_label=c.serving_label,
        serving_count=c.serving_count,
        quick=c.item_id is None,
        nutrients=nutrients(day_service.component_nutrients(c)),
    )


def entry(e: MealEntry, language: str, person: uuid.UUID | None = None) -> EntryOut:
    """An entry as seen in one person's column (their state, share and intake)."""
    part = day_service.participant_of(e, person) if person else None
    return EntryOut(
        id=e.id,
        day=e.day,
        slot=e.slot,
        at=e.at,
        name=e.name,
        eaten_out=e.eaten_out,
        saved_meal_id=e.recipe_id,
        state=part.state if part else None,
        share=part.share if part else None,
        components=[component(c, language) for c in e.components],
        intake=totals(day_service.participant_intake(e, part)) if part else None,
    )


def day(result: day_service.DayResult, language: str, viewer: uuid.UUID) -> DayOut:
    return DayOut(
        day=result.day,
        people=[
            PersonDayOut(
                user_id=p.user.id,
                display_name=p.user.display_name,
                is_me=p.user.id == viewer,
                day_type=p.day_type.value,
                targets=targets(p.targets),
                logged=totals(p.logged),
                planned=totals(p.planned),
                remaining=targets(p.remaining),
                projection=targets(p.projection),
                entries=[entry(e, language, p.user.id) for e in p.entries],
            )
            for p in result.people
        ],
    )


def target_plan(p: TargetPlan) -> TargetPlanOut:
    return TargetPlanOut(
        week_pattern=p.week_pattern,
        history=[
            TargetSetOut(
                valid_from=s.valid_from, day_type=s.day_type.value, targets=targets(s.targets)
            )
            for s in p.history
        ],
    )


def saved_meal(r: Recipe, language: str) -> SavedMealOut:
    return SavedMealOut(
        id=r.id,
        name=r.name,
        ingredients=[
            IngredientOut(
                item_id=i.item_id,
                name=display_name(_names(i.item), language),
                amount=i.amount,
                base_unit=i.item.base_unit,
            )
            for i in r.ingredients
        ],
        per_serving=totals(saved_meals.nutrition(r)),
    )


def snapshot(s: Snapshot, language: str, viewer: uuid.UUID) -> SnapshotOut:
    return SnapshotOut(
        today=day(s.today, language, viewer),
        tonight=[entry(e, language) for e in s.tonight],
        shopping_list=shopping_list(s.shopping_list, s.stores, clock.now()),
        not_yet_available=list(s.not_yet_available),
    )


def store(s: Store) -> StoreOut:
    return StoreOut(id=s.id, key=s.key, name=s.name, custom=s.household_id is not None)


def list_item(r: ShoppingListItem) -> ListItemOut:
    return ListItemOut(
        id=r.id,
        text=r.text,
        item_id=r.item_id,
        quantity=r.quantity,
        store_id=r.store_id,
        category=r.category,
        checked=r.checked,
        checked_at=r.checked_at,
        checked_by=r.checked_by,
        created_by=r.created_by,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def shopping_list(rows: list[ShoppingListItem], stores: list[Store], now: datetime) -> ListOut:
    return ListOut(
        items=[list_item(r) for r in rows], stores=[store(s) for s in stores], server_time=now
    )


def list_memory(m: ListMemory) -> ListMemoryOut:
    return ListMemoryOut(
        text=m.text, item_id=m.item_id, category=m.category, store_id=m.store_id, uses=m.uses
    )


def list_op_result(r: shopping_service.OpResult) -> ListOpResultOut:
    return ListOpResultOut(id=r.id, status=r.status, code=r.code)
