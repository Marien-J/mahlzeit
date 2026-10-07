from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import PantryCheckIn, PurchaseIn, StockAdjustIn, TrackingModeIn
from mahlzeit.domain.catalogue import TrackingMode
from mahlzeit.domain.stock import Status
from mahlzeit.services import stock
from mahlzeit.services.targets import today_for

router = APIRouter(tags=["stock"])


@router.post("/purchases", response_model=views.PurchaseOut, status_code=status.HTTP_201_CREATED)
def record_purchase(body: PurchaseIn, current: CurrentWrite, db: Db) -> views.PurchaseOut:
    """One shop: 'Bought' from the checked list items, by barcode or by hand. Food goes into
    stock and the list items it came from leave the list. Sending it again changes nothing."""
    purchase = stock.record_purchase(
        db, current.actor, convert.purchase_input(body), language=current.user.language
    )
    return views.purchase(purchase)


@router.get("/purchases", response_model=list[views.PurchaseOut])
def list_purchases(current: Current, db: Db) -> list[views.PurchaseOut]:
    """The latest purchases, newest first."""
    return [views.purchase(p) for p in stock.list_purchases(db, current.actor)]


@router.get("/purchases/{purchase_id}", response_model=views.PurchaseOut)
def get_purchase(purchase_id: uuid.UUID, current: Current, db: Db) -> views.PurchaseOut:
    return views.purchase(stock.get_purchase(db, current.actor, purchase_id))


@router.get("/stock", response_model=views.StockOut)
def get_stock(current: Current, db: Db, category: str | None = None) -> views.StockOut:
    """What is in the house, aisle by aisle, and when each aisle was last checked."""
    return views.stock_view(
        stock.get_stock(db, current.actor, language=current.user.language, category=category)
    )


@router.get("/stock/report", response_model=views.StockReportOut)
def stock_report(
    current: Current, db: Db, start: date | None = None, end: date | None = None
) -> views.StockReportOut:
    """Purchased, logged, wasted and corrected per item; the last 30 days by default."""
    last = end or today_for(current.user)
    first = start or last - timedelta(days=29)
    return views.stock_report(
        stock.report(db, current.actor, start=first, end=last, language=current.user.language)
    )


@router.get("/stock/items/{item_id}", response_model=views.ItemStockOut)
def item_stock(item_id: uuid.UUID, current: Current, db: Db) -> views.ItemStockOut:
    """One item's stock and its latest movements."""
    row = stock.item_stock(db, current.actor, item_id, language=current.user.language)
    moved = stock.movements(db, current.actor, item_id)
    return views.ItemStockOut(
        stock=views.stock_row(row), movements=[views.stock_movement(m) for m in moved]
    )


@router.post("/stock/items/{item_id}/adjust", response_model=views.StockRowOut)
def adjust_stock(
    item_id: uuid.UUID, body: StockAdjustIn, current: CurrentWrite, db: Db
) -> views.StockRowOut:
    """Fix one item: what is there now, what was thrown away, found more, or its status."""
    row = stock.adjust(
        db,
        current.actor,
        item_id,
        count=body.count,
        waste=body.waste,
        add=body.add,
        status=Status(body.status) if body.status else None,
        language=current.user.language,
    )
    return views.stock_row(row)


@router.put("/stock/items/{item_id}/mode", response_model=views.StockRowOut)
def set_tracking_mode(
    item_id: uuid.UUID, body: TrackingModeIn, current: CurrentWrite, db: Db
) -> views.StockRowOut:
    mode = TrackingMode(body.mode) if body.mode else None
    row = stock.set_mode(db, current.actor, item_id, mode, language=current.user.language)
    return views.stock_row(row)


@router.post("/stock/checks", response_model=views.PantryCheckOut)
def check_aisle(body: PantryCheckIn, current: CurrentWrite, db: Db) -> views.PantryCheckOut:
    """The pantry check of one aisle: the amounts and statuses fixed, the aisle marked checked."""
    check = stock.check_category(
        db,
        current.actor,
        body.category,
        counts=body.counts,
        statuses={k: Status(v) for k, v in body.statuses.items()},
    )
    return views.pantry_check(check)


@router.get("/list/suggestions", response_model=views.SuggestionsOut)
def list_suggestions(current: Current, db: Db) -> views.SuggestionsOut:
    """Suggested for the list, never added by itself: what planned meals need beyond stock,
    staples low or out, usual purchases not in stock."""
    found = stock.suggestions(db, current.actor, language=current.user.language)
    return views.suggestions(stock.plan_days(db, current.actor), found)
