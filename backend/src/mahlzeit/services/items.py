"""The catalogue: generic seed foods plus each household's own items."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import Float, case, cast, exists, func, literal, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.domain import catalogue as rules
from mahlzeit.domain.catalogue import BaseUnit, Category, TrackingMode
from mahlzeit.domain.errors import Conflict, NotFound
from mahlzeit.domain.nutrition import NUTRIENTS, Nutrients
from mahlzeit.domain.off import ItemDraft, map_product
from mahlzeit.domain.permissions import Actor
from mahlzeit.domain.search import normalize
from mahlzeit.models import (
    Favourite,
    Item,
    ItemBarcode,
    MealComponent,
    MealEntry,
    OffCache,
    ServingSize,
)
from mahlzeit.off_client import OffClient, OffUnavailable
from mahlzeit.services import audit, ratelimit

SEARCH_LIMIT = 25
FOUND_TTL = timedelta(days=30)
NOT_FOUND_TTL = timedelta(days=1)
OFF_READS_PER_MINUTE = 15
OFF_SEARCHES_PER_MINUTE = 10


@dataclass
class ItemInput:
    names: dict[str, str | None]
    brand: str | None = None
    category: Category = Category.OTHER
    base_unit: BaseUnit = BaseUnit.G
    nutrients: Nutrients = field(default_factory=Nutrients)
    package_size: float | None = None
    servings: list[tuple[str, float]] = field(default_factory=list)
    barcodes: list[str] = field(default_factory=list)
    tracking_mode: TrackingMode = TrackingMode.COUNTED
    image_url: str | None = None


@dataclass(frozen=True)
class Hit:
    item: Item
    favourite: bool
    uses: int


@dataclass(frozen=True)
class BarcodeResult:
    item: Item | None = None
    draft: ItemDraft | None = None

    @property
    def status(self) -> str:
        return "item" if self.item else "draft" if self.draft else "not_found"


def search_text_for(item: Item) -> str:
    parts = [item.name_de, item.name_en, item.name_nl, item.brand]
    return normalize(" ".join(p for p in parts if p))


def nutrients_of(item: Item) -> Nutrients:
    return Nutrients(**{n: getattr(item, n) for n in NUTRIENTS})


def _visible(actor: Actor) -> Any:
    return or_(Item.household_id.is_(None), Item.household_id == actor.household_id)


def get(db: Session, actor: Actor, item_id: uuid.UUID) -> Item:
    item = db.scalars(
        select(Item)
        .where(Item.id == item_id, _visible(actor))
        .options(selectinload(Item.barcodes), selectinload(Item.servings))
    ).first()
    if item is None:
        raise NotFound("item_not_found")
    return item


def favourite_ids(db: Session, actor: Actor) -> set[uuid.UUID]:
    return set(db.scalars(select(Favourite.item_id).where(Favourite.user_id == actor.user_id)))


def search(db: Session, actor: Actor, query: str, *, limit: int = SEARCH_LIMIT) -> list[Hit]:
    """Typo-tolerant search over all three languages. The household's own and often used
    items rank first, then generic foods. With an empty query: favourites and recent items."""
    q = normalize(query)
    since = clock.now().date() - timedelta(days=90)
    uses = (
        select(MealComponent.item_id, func.count().label("n"))
        .join(MealEntry, MealEntry.id == MealComponent.entry_id)
        .where(MealEntry.household_id == actor.household_id, MealEntry.day >= since)
        .group_by(MealComponent.item_id)
        .subquery()
    )
    is_fav = exists().where(Favourite.item_id == Item.id, Favourite.user_id == actor.user_id)
    used = func.coalesce(uses.c.n, 0)
    sim: ColumnElement[float]
    if q:
        sim = func.greatest(
            func.similarity(Item.search_text, q), func.word_similarity(q, Item.search_text)
        )
        match = or_(sim >= 0.3, Item.search_text.like(f"%{q}%"))
    else:
        sim = cast(literal(0.0), Float)
        match = or_(is_fav, used > 0)
    score = (
        sim
        + func.least(func.ln(1 + used) * 0.08, 0.3)
        + case((is_fav, 0.15), else_=0.0)
        + case((Item.household_id.is_not(None), 0.2), else_=0.0)
    )
    rows = db.execute(
        select(Item, is_fav, used)
        .outerjoin(uses, uses.c.item_id == Item.id)
        .where(_visible(actor), match)
        .order_by(score.desc(), Item.search_text)
        .limit(limit)
        .options(selectinload(Item.servings), selectinload(Item.barcodes))
    ).all()
    return [Hit(item=item, favourite=bool(fav), uses=int(n)) for item, fav, n in rows]


def _apply(item: Item, data: ItemInput) -> None:
    names = rules.check_names(data.names)
    rules.check_label(data.nutrients)
    item.name_de, item.name_en, item.name_nl = names.get("de"), names.get("en"), names.get("nl")
    item.brand = (data.brand or "").strip()[:80] or None
    item.category = Category(data.category).value
    item.base_unit = BaseUnit(data.base_unit).value
    item.tracking_mode = TrackingMode(data.tracking_mode).value
    item.package_size = data.package_size if data.package_size and data.package_size > 0 else None
    item.image_url = data.image_url
    for name, value in data.nutrients.items():
        setattr(item, name, value)
    item.search_text = search_text_for(item)
    item.updated_at = clock.now()
    servings = [rules.check_serving(label, amount) for label, amount in data.servings]
    item.servings = [
        ServingSize(label=lbl, amount=amt, position=i) for i, (lbl, amt) in enumerate(servings)
    ]


def _set_barcodes(db: Session, actor: Actor, item: Item, codes: list[str]) -> None:
    wanted = {rules.check_barcode(c) for c in codes}
    taken = db.scalars(
        select(ItemBarcode).where(
            ItemBarcode.household_id == actor.household_id,
            ItemBarcode.code.in_(wanted),
            ItemBarcode.item_id != item.id,
        )
    ).first()
    if taken is not None:
        raise Conflict("barcode_taken", barcode=taken.code)
    item.barcodes = [b for b in item.barcodes if b.code in wanted] + [
        ItemBarcode(household_id=actor.household_id, code=c)
        for c in sorted(wanted - {b.code for b in item.barcodes})
    ]


def _snapshot(item: Item) -> dict[str, Any]:
    return {
        "names": {"de": item.name_de, "en": item.name_en, "nl": item.name_nl},
        "brand": item.brand,
        "category": item.category,
        "nutrients": nutrients_of(item).as_dict(),
    }


def create(
    db: Session,
    actor: Actor,
    data: ItemInput,
    *,
    source: str = "custom",
    source_id: str | None = None,
) -> Item:
    item = Item(
        household_id=actor.household_id,
        source=source,
        source_id=source_id,
        created_by=actor.user_id,
    )
    _apply(item, data)
    db.add(item)
    db.flush()
    _set_barcodes(db, actor, item, data.barcodes)
    audit.record(
        db, actor=actor, entity="item", entity_id=item.id, action="created", after=_snapshot(item)
    )
    db.commit()
    return get(db, actor, item.id)


def update(db: Session, actor: Actor, item_id: uuid.UUID, data: ItemInput) -> Item:
    item = get(db, actor, item_id)
    if item.household_id is None:
        raise Conflict("item_read_only")
    before = _snapshot(item)
    _apply(item, data)
    _set_barcodes(db, actor, item, data.barcodes)
    audit.record(
        db,
        actor=actor,
        entity="item",
        entity_id=item.id,
        action="updated",
        before=before,
        after=_snapshot(item),
    )
    db.commit()
    return get(db, actor, item.id)


def set_favourite(db: Session, actor: Actor, item_id: uuid.UUID, on: bool) -> None:
    get(db, actor, item_id)
    current = db.get(Favourite, (actor.user_id, item_id))
    if on and current is None:
        db.add(Favourite(user_id=actor.user_id, item_id=item_id))
    elif not on and current is not None:
        db.delete(current)
    else:
        return
    audit.record(
        db, actor=actor, entity="favourite", entity_id=item_id, action="added" if on else "removed"
    )
    db.commit()


def lookup_barcode(db: Session, actor: Actor, code: str, off: OffClient) -> BarcodeResult:
    """The household's item for a barcode, else an import draft from Open Food Facts."""
    code = rules.check_barcode(code)
    own = db.scalars(
        select(ItemBarcode).where(
            ItemBarcode.household_id == actor.household_id, ItemBarcode.code == code
        )
    ).first()
    if own is not None:
        return BarcodeResult(item=get(db, actor, own.item_id))
    if not get_settings().off_enabled:
        return BarcodeResult()
    now = clock.now()
    cached = db.get(OffCache, code)
    fresh = cached is not None and now - cached.fetched_at < (
        FOUND_TTL if cached.found else NOT_FOUND_TTL
    )
    if not fresh:
        ratelimit.take(db, "off:read", per_minute=OFF_READS_PER_MINUTE)
        try:
            raw = off.product(code)
        except OffUnavailable as err:
            raise Conflict("off_unavailable") from err
        draft = map_product(raw)
        if cached is None:
            cached = OffCache(code=code, found=False)
            db.add(cached)
        cached.found, cached.payload, cached.fetched_at = draft is not None, raw, now
        db.commit()
    assert cached is not None
    draft = map_product(cached.payload or {}) if cached.found else None
    return BarcodeResult(draft=draft)


def search_online(
    db: Session, actor: Actor, query: str, language: str, off: OffClient
) -> list[ItemDraft]:
    """The explicit 'search online' action. Never called while the person types."""
    q = query.strip()
    if len(q) < 2 or not get_settings().off_enabled:
        return []
    ratelimit.take(db, "off:search", per_minute=OFF_SEARCHES_PER_MINUTE)
    try:
        hits = off.search(q, language)
    except OffUnavailable as err:
        raise Conflict("off_unavailable") from err
    drafts = [map_product({"status": "success", "code": h.get("code"), "product": h}) for h in hits]
    return [d for d in drafts if d is not None and d.names]
