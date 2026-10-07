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
from mahlzeit.domain.nutrition import Nutrients, Totals, rounded, total
from mahlzeit.domain.off import ItemDraft
from mahlzeit.domain.targets import Targets
from mahlzeit.models import (
    Item,
    ListMemory,
    MealComponent,
    MealEntry,
    MealParticipant,
    PantryCheck,
    Purchase,
    Recipe,
    ShoppingListItem,
    StockMovement,
    Store,
)
from mahlzeit.services import day as day_service
from mahlzeit.services import items as item_service
from mahlzeit.services import offers as offer_service
from mahlzeit.services import recipes
from mahlzeit.services import shopping as shopping_service
from mahlzeit.services import stock as stock_service
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


class ParticipantOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    state: Literal["planned", "logged", "skipped"]
    share: float
    exact_amounts: dict[uuid.UUID, float]
    intake: TotalsOut


class EntryOut(BaseModel):
    id: uuid.UUID
    day: date
    slot: Literal["breakfast", "lunch", "dinner", "snack"]
    at: time
    name: str | None
    eaten_out: bool
    recipe_id: uuid.UUID | None
    recipe_portions: float | None
    joint: bool
    state: Literal["planned", "logged", "skipped"] | None
    share: float | None
    components: list[ComponentOut]
    participants: list[ParticipantOut]
    intake: TotalsOut | None
    dish: TotalsOut


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


class RecipeOut(BaseModel):
    id: uuid.UUID
    kind: Literal["recipe", "saved_meal"]
    name: str
    servings: float
    cooked_yield_g: float | None
    staple: bool
    notes: str | None
    ingredients: list[IngredientOut]
    per_serving: TotalsOut
    per_100g_cooked: NutrientsOut | None


class AddedToListOut(BaseModel):
    added: list[ListItemOut]
    already_listed: list[str]
    in_stock: list[str]


class PlanDayOut(BaseModel):
    day: date
    entries: list[EntryOut]


class PlanMemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    is_me: bool


class OfferEffectOut(BaseModel):
    incoming: TotalsOut
    targets: TargetsOut | None
    projection_before: TargetsOut | None
    projection_after: TargetsOut | None


class OfferOut(BaseModel):
    id: uuid.UUID
    state: Literal["pending", "accepted", "declined", "countered", "withdrawn", "expired"]
    from_user_id: uuid.UUID
    from_name: str
    to_user_id: uuid.UUID
    to_name: str
    incoming: bool
    day: date
    slot: Literal["breakfast", "lunch", "dinner", "snack"]
    share: float
    counter_of_id: uuid.UUID | None
    created_at: datetime
    responded_at: datetime | None
    meal: EntryOut | None
    effect: OfferEffectOut | None


class PlanOut(BaseModel):
    members: list[PlanMemberOut]
    days: list[PlanDayOut]
    offers: list[OfferOut]


class SnapshotOut(BaseModel):
    today: DayOut
    tonight: list[EntryOut]
    offers: list[OfferOut]
    shopping_list: ListOut
    stock: StockSummaryOut
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


# --- stock --------------------------------------------------------------------------------

Unit = Literal["g", "ml"]
StatusName = Literal["ok", "low", "out"]


class StockRowOut(BaseModel):
    item_id: uuid.UUID
    name: str
    category: str
    base_unit: Unit
    mode: Literal["counted", "status"]
    level: float | None  # counted items, never below zero
    status: StatusName | None  # status-only items
    step: float  # one tap of the pantry stepper
    package_size: float | None
    last_moved: date | None


class PantryCheckOut(BaseModel):
    category: str
    checked_at: datetime
    checked_by: uuid.UUID | None


class StockOut(BaseModel):
    rows: list[StockRowOut]
    checks: list[PantryCheckOut]


class StockMovementOut(BaseModel):
    id: uuid.UUID
    amount: float
    reason: Literal["purchase", "consumption", "correction", "waste"]
    source: Literal["purchase", "entry", "shortfall", "pantry", "manual"]
    source_id: uuid.UUID | None
    day: date
    created_by: uuid.UUID | None
    created_at: datetime


class ItemStockOut(BaseModel):
    stock: StockRowOut
    movements: list[StockMovementOut]


class StockSummaryOut(BaseModel):
    in_stock: list[StockRowOut]
    low: list[str]
    out: list[str]


class PurchaseLineOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID | None
    text: str
    quantity: str | None
    amount: float | None
    base_unit: Unit | None
    price_cents: int | None
    list_item_id: uuid.UUID | None


class PurchaseOut(BaseModel):
    id: uuid.UUID
    day: date
    store_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    lines: list[PurchaseLineOut]
    spend_cents: int | None


class SuggestionOut(BaseModel):
    item_id: uuid.UUID
    name: str
    category: str
    base_unit: Unit
    reason: Literal["planned", "low", "out", "usual"]
    quantity: str | None
    amount: float | None


class SuggestionsOut(BaseModel):
    plan_days: int
    suggestions: list[SuggestionOut]


class StockReportRowOut(BaseModel):
    item_id: uuid.UUID
    name: str
    base_unit: Unit
    purchased: float
    logged: float
    wasted: float
    corrected: float
    shortfall: float
    level: float | None
    spend_cents: int | None


class StockReportOut(BaseModel):
    start: date
    end: date
    rows: list[StockReportRowOut]
    spend_cents: int


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


def participant(e: MealEntry, p: MealParticipant) -> ParticipantOut:
    return ParticipantOut(
        user_id=p.user_id,
        display_name=p.user.display_name,
        state=p.state,
        share=round(p.share, 4),
        exact_amounts={x.component_id: x.amount for x in p.exact_amounts},
        intake=totals(day_service.participant_intake(e, p)),
    )


def entry(e: MealEntry, language: str, person: uuid.UUID | None = None) -> EntryOut:
    """An entry as seen in one person's column (their state, share and intake). Without a
    person it is the meal itself, with everyone who is on it."""
    part = day_service.participant_of(e, person) if person else None
    return EntryOut(
        id=e.id,
        day=e.day,
        slot=e.slot,
        at=e.at,
        name=e.name,
        eaten_out=e.eaten_out,
        recipe_id=e.recipe_id,
        recipe_portions=e.recipe_portions,
        joint=len(e.participants) > 1,
        state=part.state if part else None,
        share=part.share if part else None,
        components=[component(c, language) for c in e.components],
        participants=[participant(e, p) for p in e.participants],
        intake=totals(day_service.participant_intake(e, part)) if part else None,
        dish=totals(total(day_service.component_nutrients(c) for c in e.components)),
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


def recipe(r: Recipe, language: str) -> RecipeOut:
    per_100 = recipes.nutrition_per_100g_cooked(r)
    return RecipeOut(
        id=r.id,
        kind=r.kind,
        name=r.name,
        servings=r.servings,
        cooked_yield_g=r.cooked_yield_g,
        staple=r.staple,
        notes=r.notes,
        ingredients=[
            IngredientOut(
                item_id=i.item_id,
                name=display_name(_names(i.item), language),
                amount=i.amount,
                base_unit=i.item.base_unit,
            )
            for i in r.ingredients
        ],
        per_serving=totals(recipes.nutrition(r)),
        per_100g_cooked=nutrients(per_100) if per_100 else None,
    )


def added_to_list(r: recipes.AddedToList) -> AddedToListOut:
    return AddedToListOut(
        added=[list_item(i) for i in r.added],
        already_listed=r.already_listed,
        in_stock=r.in_stock,
    )


def plan(
    result: day_service.PlanResult,
    offers: list[offer_service.OfferView],
    language: str,
    viewer: uuid.UUID,
) -> PlanOut:
    return PlanOut(
        members=[
            PlanMemberOut(user_id=m.id, display_name=m.display_name, is_me=m.id == viewer)
            for m in result.members
        ],
        days=[
            PlanDayOut(day=d.day, entries=[entry(e, language) for e in d.entries])
            for d in result.days
        ],
        offers=[offer(v, language, viewer) for v in offers],
    )


def offer_effect(e: offer_service.Effect) -> OfferEffectOut:
    return OfferEffectOut(
        incoming=totals(e.incoming),
        targets=targets(e.targets),
        projection_before=targets(e.projection_before),
        projection_after=targets(e.projection_after),
    )


def offer(v: offer_service.OfferView, language: str, viewer: uuid.UUID) -> OfferOut:
    o = v.offer
    return OfferOut(
        id=o.id,
        state=v.state.value,
        from_user_id=o.from_user_id,
        from_name=v.sender.display_name,
        to_user_id=o.to_user_id,
        to_name=v.receiver.display_name,
        incoming=o.to_user_id == viewer,
        day=o.day,
        slot=o.slot,
        share=o.share,
        counter_of_id=o.counter_of_id,
        created_at=o.created_at,
        responded_at=o.responded_at,
        meal=entry(v.entry, language) if v.entry else None,
        effect=offer_effect(v.effect) if v.effect else None,
    )


def snapshot(s: Snapshot, language: str, viewer: uuid.UUID) -> SnapshotOut:
    return SnapshotOut(
        today=day(s.today, language, viewer),
        tonight=[entry(e, language) for e in s.tonight],
        offers=[offer(v, language, viewer) for v in s.offers],
        shopping_list=shopping_list(s.shopping_list, s.stores, clock.now()),
        stock=stock_summary(s.stock),
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


def _amount(value: float) -> float:
    return round(value, 1)


def stock_row(r: stock_service.StockRow) -> StockRowOut:
    return StockRowOut(
        item_id=r.item.id,
        name=r.name,
        category=r.item.category,
        base_unit=r.item.base_unit,
        mode=r.mode.value,
        level=None if r.level is None else _amount(r.level),
        status=r.status.value if r.status else None,
        step=r.step,
        package_size=r.item.package_size,
        last_moved=r.last_moved,
    )


def pantry_check(c: PantryCheck) -> PantryCheckOut:
    return PantryCheckOut(category=c.category, checked_at=c.checked_at, checked_by=c.checked_by)


def stock_view(v: stock_service.StockView) -> StockOut:
    return StockOut(
        rows=[stock_row(r) for r in v.rows], checks=[pantry_check(c) for c in v.checks.values()]
    )


def stock_movement(m: StockMovement) -> StockMovementOut:
    return StockMovementOut(
        id=m.id,
        amount=_amount(m.amount),
        reason=m.reason,
        source=m.source,
        source_id=m.source_id,
        day=m.day,
        created_by=m.created_by,
        created_at=m.created_at,
    )


def stock_summary(s: stock_service.Summary) -> StockSummaryOut:
    return StockSummaryOut(in_stock=[stock_row(r) for r in s.in_stock], low=s.low, out=s.out)


def purchase(p: Purchase) -> PurchaseOut:
    prices = [ln.price_cents for ln in p.lines if ln.price_cents is not None]
    return PurchaseOut(
        id=p.id,
        day=p.day,
        store_id=p.store_id,
        created_by=p.created_by,
        created_at=p.created_at,
        lines=[
            PurchaseLineOut(
                id=ln.id,
                item_id=ln.item_id,
                text=ln.text,
                quantity=ln.quantity,
                amount=None if ln.amount is None else _amount(ln.amount),
                base_unit=ln.item.base_unit if ln.item else None,
                price_cents=ln.price_cents,
                list_item_id=ln.list_item_id,
            )
            for ln in p.lines
        ],
        spend_cents=sum(prices) if prices else None,
    )


def suggestions(plan_days: int, found: list[stock_service.Suggestion]) -> SuggestionsOut:
    return SuggestionsOut(
        plan_days=plan_days,
        suggestions=[
            SuggestionOut(
                item_id=x.item.id,
                name=x.name,
                category=x.item.category,
                base_unit=x.item.base_unit,
                reason=x.reason,
                quantity=x.quantity,
                amount=None if x.amount is None else _amount(x.amount),
            )
            for x in found
        ],
    )


def stock_report(r: stock_service.Report) -> StockReportOut:
    return StockReportOut(
        start=r.start,
        end=r.end,
        rows=[
            StockReportRowOut(
                item_id=x.item.id,
                name=x.name,
                base_unit=x.item.base_unit,
                purchased=_amount(x.purchased),
                logged=_amount(x.logged),
                wasted=_amount(x.wasted),
                corrected=_amount(x.corrected),
                shortfall=_amount(x.shortfall),
                level=None if x.level is None else _amount(x.level),
                spend_cents=x.spend_cents,
            )
            for x in r.rows
        ],
        spend_cents=r.spend_cents,
    )
